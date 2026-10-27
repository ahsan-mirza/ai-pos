"""Repair workshop: status timeline, parts and labour on the ticket, and invoicing them as a normal sale."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.pagination import count_rows
from app.core.permissions import Permission
from app.models.product import Product
from app.models.purchasing import PurchaseOrderLine
from app.models.repair_ticket import RepairDeposit, RepairEvent, RepairLine, RepairTicket
from app.models.sale import Sale
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import (
    PriceOverridePayload,
    RepairOut,
    RepairPayload,
    SaleItemPayload,
    SalePayload,
    SaleTenderPayload,
)
from app.schemas.repairs import (
    RepairDetail,
    RepairDeviceHit,
    RepairEventOut,
    RepairInvoiceCreate,
    RepairLineCreate,
    RepairLineOut,
    RepairStatusChange,
)
from app.services import repair_workshop_service
from app.services.catalog_service import _repair_out, get_repair
from app.services.identifiers import identifier_hash, normalize_identifier
from app.services.phone_numbers import search_terms
from app.services.product_search import search_products
from app.services.sale_service import record_sale
from app.services.sync_service import notify_repair_ready
from app.services.tax import line_tax
from app.services.tax import policy as tax_policy_for

LABOUR_SKU = "SRV-REPAIR-LABOUR"
FINAL = ("closed", "cancelled")
# A warning only. The shop decides; nothing is written off or discounted automatically.
VALUE_WARNING_RATIO = 0.5


def _purchase_cost(db: Session, product_id: uuid.UUID) -> int | None:
    cost = db.scalar(
        select(PurchaseOrderLine.unit_cost_cents)
        .where(PurchaseOrderLine.product_id == product_id, PurchaseOrderLine.unit_cost_cents > 0)
        .order_by(PurchaseOrderLine.id.desc())
        .limit(1)
    )
    return int(cost) if cost else None


def assert_device(db: Session, data: RepairPayload, digest: str, ignore_id: uuid.UUID | None) -> None:
    """Shop equipment must be a real catalog item. Booking never changes that item's stock."""
    if data.ownership != "internal":
        return
    product = db.get(Product, data.product_id) if data.product_id else None
    if product is None:
        raise SyncRejected("Select a device that is in inventory.")
    serial = db.scalar(select(SerialNumber).where(SerialNumber.value_hash == digest).limit(1))
    if serial is not None and serial.status == "sold":
        raise SyncRejected("That unit was sold. Book it as a customer repair.")
    if serial is not None and serial.product_id != product.id:
        raise SyncRejected("That serial belongs to a different product.")
    if product.is_serialized and serial is None:
        raise SyncRejected("Enter the serial number of the shop device.")
    open_filter = [
        RepairTicket.product_id == product.id,
        RepairTicket.identifier_hash == digest,
        RepairTicket.status.notin_(FINAL),
    ]
    if ignore_id is not None:
        open_filter.append(RepairTicket.id != ignore_id)
    open_job = db.scalar(select(RepairTicket.id).where(*open_filter))
    if open_job is not None:
        raise SyncRejected("That device is already in the workshop.")


def search_devices(db: Session, query: str, *, limit: int, store_id: uuid.UUID | None) -> list[RepairDeviceHit]:
    hits = []
    for found in search_products(db, query, limit=limit, store_id=store_id):
        product = found.product
        cost = _purchase_cost(db, product.id)
        warning = None
        available = True
        if found.serial_status == "sold":
            available = False
            warning = "Sold. Book this as a customer repair, not shop equipment."
        hits.append(
            RepairDeviceHit(
                product_id=product.id,
                name=product.name,
                sku=product.sku,
                selling_price_cents=product.price_cents,
                purchase_cost_cents=cost,
                serial_status=found.serial_status,
                available=available,
                warning=warning,
            )
        )
    return hits


STATUSES = (
    "intake",
    "diagnosing",
    "awaiting_approval",
    "in_repair",
    "waiting_parts",
    "ready",
    "closed",
    "cancelled",
)
SORTS = {
    "received": RepairTicket.created_at,
    "promised": RepairTicket.promised_at,
    "status": RepairTicket.status,
    "customer": RepairTicket.customer_name,
    "estimate": RepairTicket.estimated_cost_cents,
    "device": RepairTicket.device_model,
}


def _filter_moment(value: str | None, name: str) -> datetime | None:
    if value is None or value.strip() == "":
        return None
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise ApiError(422, "invalid_filter", f"{name} must be a date.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _search_clause(query: str):
    needle = query.strip()
    if needle == "":
        return None
    folded = f"%{needle.casefold()}%"
    clauses = [
        func.lower(RepairTicket.customer_name).like(folded),
        func.lower(RepairTicket.device_model).like(folded),
        func.lower(RepairTicket.issue).like(folded),
        func.lower(cast(RepairTicket.id, String)).like(f"{needle.casefold()}%"),
    ]
    digits = "".join(char for char in needle if char.isdigit())
    terms = search_terms(needle)
    if len(digits) >= 6 and digits not in terms:
        terms.append(digits)
    for term in terms:
        clauses.append(RepairTicket.customer_phone.like(f"%{term.lstrip('+')}%"))
    for kind in ("imei", "serial"):
        try:
            normalized = normalize_identifier(kind, needle)
        except SyncRejected:
            continue
        clauses.append(RepairTicket.identifier_hash == identifier_hash(normalized))
    return or_(*clauses)


def _checked(value: str | None, allowed: tuple[str, ...] | set[str], name: str) -> str | None:
    if value is None or value == "":
        return None
    if value not in allowed:
        raise ApiError(422, "invalid_filter", f"{name} is not a supported value.")
    return value


def search_tickets(
    db: Session,
    settings: Settings,
    *,
    store_scope: uuid.UUID | None,
    store_id: uuid.UUID | None = None,
    query: str = "",
    status: str | None = None,
    ownership: str | None = None,
    technician_id: uuid.UUID | None = None,
    received_from: str | None = None,
    received_to: str | None = None,
    promised_from: str | None = None,
    promised_to: str | None = None,
    overdue: bool = False,
    warranty: bool = False,
    active: bool = False,
    sort: str = "received",
    direction: str = "desc",
    offset: int = 0,
    limit: int = 25,
    financial: bool = False,
) -> tuple[list[RepairOut], int]:
    """One page of persisted tickets. Search and filters apply before pagination."""
    status = _checked(status, STATUSES, "Status")
    ownership = _checked(ownership, ("customer", "internal"), "Repair type")
    sort_name = _checked(sort, set(SORTS), "Sort") or "received"
    direction = _checked(direction, ("asc", "desc"), "Sort direction") or "desc"
    statement = select(RepairTicket)
    scope = store_scope if store_scope is not None else store_id
    if scope is not None:
        statement = statement.where(RepairTicket.store_id == scope)
    found = _search_clause(query)
    if found is not None:
        statement = statement.where(found)
    if status is not None:
        statement = statement.where(RepairTicket.status == status)
    if active:
        statement = statement.where(RepairTicket.status.notin_(FINAL))
    if ownership is not None:
        statement = statement.where(RepairTicket.ownership == ownership)
    if technician_id is not None:
        statement = statement.where(RepairTicket.technician_id == technician_id)
    if warranty:
        statement = statement.where(RepairTicket.warranty_status == "IN_WARRANTY")
    start = _filter_moment(received_from, "Received from")
    end = _filter_moment(received_to, "Received to")
    if received_to and len(received_to.strip()) == 10 and end is not None:
        end = end + timedelta(days=1)
    if start is not None:
        statement = statement.where(RepairTicket.created_at >= start)
    if end is not None:
        received_column = RepairTicket.created_at
        date_only = len((received_to or "").strip()) == 10
        statement = statement.where(received_column < end if date_only else received_column <= end)
    promise_start = _filter_moment(promised_from, "Expected from")
    promise_end = _filter_moment(promised_to, "Expected to")
    if promised_to and len(promised_to.strip()) == 10 and promise_end is not None:
        promise_end = promise_end + timedelta(days=1)
    if promise_start is not None:
        statement = statement.where(RepairTicket.promised_at >= promise_start)
    if promise_end is not None:
        inclusive = len((promised_to or "").strip()) != 10
        column = RepairTicket.promised_at
        statement = statement.where(column <= promise_end if inclusive else column < promise_end)
    if overdue:
        statement = statement.where(
            RepairTicket.promised_at.is_not(None),
            RepairTicket.promised_at < datetime.now(UTC),
            RepairTicket.status.notin_(FINAL),
        )
    total = count_rows(db, statement)
    column = SORTS[sort_name]
    ordered = column.asc() if direction == "asc" else column.desc()
    rows = list(db.scalars(statement.order_by(ordered, RepairTicket.id).offset(offset).limit(limit)))
    return _list_page(db, settings, rows, financial), total


def _list_page(db: Session, settings: Settings, rows: list[RepairTicket], financial: bool) -> list[RepairOut]:
    if not rows:
        return []
    ids = [row.id for row in rows]
    held = {
        ticket_id: int(amount)
        for ticket_id, amount in db.execute(
            select(RepairDeposit.ticket_id, func.coalesce(func.sum(RepairDeposit.amount_cents), 0))
            .where(RepairDeposit.ticket_id.in_(ids), RepairDeposit.status == "HELD")
            .group_by(RepairDeposit.ticket_id)
        ).all()
    }
    tech_ids = {row.technician_id for row in rows if row.technician_id is not None}
    names: dict[uuid.UUID, str] = {}
    if tech_ids:
        names = {
            user_id: name
            for user_id, name in db.execute(select(User.id, User.full_name).where(User.id.in_(tech_ids))).all()
        }
    costs: dict[uuid.UUID, dict[str, int]] = {}
    if financial:
        amounts = db.execute(
            select(
                RepairLine.ticket_id,
                RepairLine.kind,
                func.coalesce(func.sum(RepairLine.quantity * RepairLine.unit_price_cents), 0),
            )
            .where(RepairLine.ticket_id.in_(ids))
            .group_by(RepairLine.ticket_id, RepairLine.kind)
        ).all()
        for ticket_id, kind, amount in amounts:
            costs.setdefault(ticket_id, {})[kind] = int(amount)
    now = datetime.now(UTC)
    listed: list[RepairOut] = []
    for row in rows:
        promised = row.promised_at
        if promised is not None and promised.tzinfo is None:
            promised = promised.replace(tzinfo=UTC)
        late = promised is not None and promised < now and row.status not in FINAL
        line_costs = costs.get(row.id, {})
        listed.append(
            _repair_out(row, settings).model_copy(
                update={
                    "technician_name": names.get(row.technician_id) if row.technician_id else None,
                    "deposit_held_cents": held.get(row.id, 0),
                    "overdue": late,
                    "parts_cents": line_costs.get("PART", 0) if financial else None,
                    "labour_cents": line_costs.get("LABOUR", 0) if financial else None,
                }
            )
        )
    return listed


def matching_open_repairs(
    db: Session,
    settings: Settings,
    *,
    store_scope: uuid.UUID | None,
    phone: str = "",
    identifier: str = "",
    customer_name: str = "",
) -> list[RepairOut]:
    """Active jobs that may be the same device or customer. Callers decide whether a new job is still legitimate."""
    clauses = []
    if phone.strip():
        for term in search_terms(phone) or ["".join(char for char in phone if char.isdigit())]:
            if term:
                clauses.append(RepairTicket.customer_phone.like(f"%{term.lstrip('+')}%"))
    if identifier.strip():
        for kind in ("imei", "serial"):
            try:
                normalized = normalize_identifier(kind, identifier.strip())
            except SyncRejected:
                continue
            clauses.append(RepairTicket.identifier_hash == identifier_hash(normalized))
    name = customer_name.strip()
    if len(name) >= 3:
        clauses.append(func.lower(RepairTicket.customer_name) == name.casefold())
    if not clauses:
        return []
    statement = select(RepairTicket).where(RepairTicket.status.notin_(FINAL), or_(*clauses))
    if store_scope is not None:
        statement = statement.where(RepairTicket.store_id == store_scope)
    rows = list(db.scalars(statement.order_by(RepairTicket.created_at.desc()).limit(5)))
    return _list_page(db, settings, rows, False)


def _value_warning(estimate: int, cost: int | None) -> str | None:
    if cost is None or cost <= 0 or estimate <= 0:
        return None
    if estimate <= int(cost * VALUE_WARNING_RATIO):
        return None
    share = round(estimate * 100 / cost)
    return f"The estimate is {share}% of the purchase cost. This is a warning only."


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _ticket(db: Session, ticket_id: uuid.UUID, store_scope: uuid.UUID | None) -> RepairTicket:
    ticket = db.get(RepairTicket, ticket_id)
    if ticket is None or (store_scope is not None and ticket.store_id != store_scope):
        raise ApiError(404, "not_found", "Repair ticket was not found.")
    return ticket


def _user(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


def _ref(ticket: RepairTicket) -> str:
    return str(ticket.id)[:8].upper()


def _editable(ticket: RepairTicket) -> None:
    if ticket.sale_id is not None:
        raise ApiError(409, "repair_invoiced", "This repair is already invoiced; its charges are final.")
    if ticket.status in FINAL:
        raise ApiError(409, "repair_closed", f"This repair is {ticket.status}.")


def detail(db: Session, settings: Settings, ticket_id: uuid.UUID, store_scope: uuid.UUID | None) -> RepairDetail:
    ticket = _ticket(db, ticket_id, store_scope)
    base = get_repair(db, settings, ticket.id)
    events = list(
        db.scalars(select(RepairEvent).where(RepairEvent.ticket_id == ticket.id).order_by(RepairEvent.created_at))
    )
    users = {
        user.id: user.full_name
        for user in db.scalars(select(User).where(User.id.in_({e.user_id for e in events if e.user_id}))).unique()
    }
    rows = db.execute(
        select(RepairLine, Product.sku)
        .join(Product, Product.id == RepairLine.product_id)
        .where(RepairLine.ticket_id == ticket.id)
        .order_by(RepairLine.created_at)
    ).all()
    lines = [
        RepairLineOut(
            id=line.id,
            kind=line.kind,  # type: ignore[arg-type]
            product_id=line.product_id,
            sku=sku,
            description=line.description,
            quantity=line.quantity,
            unit_price_cents=line.unit_price_cents,
            line_cents=line.quantity * line.unit_price_cents,
        )
        for line, sku in rows
    ]
    sale = db.get(Sale, ticket.sale_id) if ticket.sale_id else None
    parts = sum(line.line_cents for line in lines if line.kind == "PART")
    labour = sum(line.line_cents for line in lines if line.kind == "LABOUR")
    payload = base.model_dump()
    payload.update(
        customer_id=ticket.customer_id,
        warranty_status=ticket.warranty_status,
        sale_id=ticket.sale_id,
        invoice_number=sale.invoice_number if sale else None,
        events=[
            RepairEventOut(
                from_status=event.from_status,
                to_status=event.to_status,
                note=event.note,
                source=event.source,
                user_name=users.get(event.user_id) if event.user_id else None,
                occurred_at=_aware(event.created_at),
            )
            for event in events
        ],
        lines=lines,
        parts_cents=parts,
        labour_cents=labour,
        total_cents=parts + labour,
    )
    plain = RepairDetail(**payload)
    enriched = repair_workshop_service.enrich(db, settings, ticket, plain)
    if ticket.product_id is not None:
        product = db.get(Product, ticket.product_id)
        cost = _purchase_cost(db, ticket.product_id)
        enriched = enriched.model_copy(
            update={
                "selling_price_cents": product.price_cents if product is not None else None,
                "purchase_cost_cents": cost,
                "value_warning": _value_warning(ticket.estimated_cost_cents, cost),
            }
        )
    if db.is_modified(ticket):
        db.commit()
    return enriched


def _move(db: Session, ticket: RepairTicket, status: str, note: str, user_id: uuid.UUID | None) -> None:
    db.add(RepairEvent(ticket_id=ticket.id, from_status=ticket.status, to_status=status, note=note, user_id=user_id))
    ticket.status = status
    store = db.get(Store, ticket.store_id)
    if store is not None:
        notify_repair_ready(db, ticket, store)


def change_status(
    db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID, data: RepairStatusChange
) -> RepairDetail:
    if principal.user is None and principal.kind != "device":
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    ticket = _ticket(db, ticket_id, principal.store_id)
    if ticket.status == data.status and not data.note.strip():
        raise ApiError(422, "no_change", f"The repair is already {data.status.replace('_', ' ')}.")
    if ticket.sale_id is not None and data.status != "closed":
        raise ApiError(409, "repair_invoiced", "An invoiced repair can only stay closed.")
    repair_workshop_service.check_transition(ticket, data.status)
    if data.status != ticket.status:
        repair_workshop_service.on_status(db, ticket, data.status)
    user_id = principal.user.id if principal.user is not None else None
    _move(db, ticket, data.status, data.note.strip(), user_id)
    db.commit()
    return detail(db, settings, ticket.id, principal.store_id)


def _labour_product(db: Session) -> Product:
    product = db.scalar(select(Product).where(Product.sku == LABOUR_SKU, Product.is_open_price.is_(True)))
    if product is None:
        product = db.scalar(
            select(Product)
            .where(Product.is_open_price.is_(True), func.lower(Product.name).like("%labour%"))
            .order_by(Product.created_at)
            .limit(1)
        )
    if product is None:
        raise ApiError(
            422,
            "labour_product_missing",
            "Create an open-price product for repair labour (e.g. SKU SRV-REPAIR-LABOUR).",
        )
    return product


def add_line(
    db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID, data: RepairLineCreate
) -> RepairDetail:
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    _editable(ticket)
    if data.kind == "PART":
        product = db.get(Product, data.product_id) if data.product_id else None
        if product is None:
            raise ApiError(422, "part_required", "Choose the part from the catalog.")
        if product.is_serialized or product.is_open_price or product.is_service:
            raise ApiError(422, "part_invalid", f"{product.name} cannot be fitted as a part.")
        description = data.description.strip() or product.name
        if ticket.ownership == "internal" and data.unit_price_cents is None:
            price = _purchase_cost(db, product.id) or 0
        else:
            price = product.price_cents if data.unit_price_cents is None else data.unit_price_cents
    else:
        product = db.get(Product, data.product_id) if data.product_id else _labour_product(db)
        if product is None or not product.is_open_price:
            raise ApiError(422, "labour_invalid", "Labour is charged with an open-price service product.")
        description = data.description.strip()
        if not description:
            raise ApiError(422, "description_required", "Describe the work, e.g. 'Screen replacement'.")
        if data.unit_price_cents is None:
            raise ApiError(422, "price_required", "Enter the labour charge.")
        price = data.unit_price_cents
    line = RepairLine(
        ticket_id=ticket.id,
        kind=data.kind,
        product_id=product.id,
        description=description,
        quantity=data.quantity,
        unit_price_cents=price,
        created_by_id=user.id,
        reserved_quantity=0,
    )
    db.add(line)
    db.flush()
    if ticket.approval_status != "DECLINED":
        repair_workshop_service.reserve_line(db, ticket, line)
    db.commit()
    return detail(db, settings, ticket.id, principal.store_id)


def remove_line(
    db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID, line_id: uuid.UUID
) -> RepairDetail:
    ticket = _ticket(db, ticket_id, principal.store_id)
    _editable(ticket)
    line = db.get(RepairLine, line_id)
    if line is None or line.ticket_id != ticket.id:
        raise ApiError(404, "not_found", "Line was not found.")
    repair_workshop_service.release_line(db, ticket, line)
    db.delete(line)
    db.commit()
    return detail(db, settings, ticket.id, principal.store_id)


def invoice(
    db: Session, settings: Settings, principal: Principal, ticket_id: uuid.UUID, data: RepairInvoiceCreate
) -> RepairDetail:
    """Rings the ticket's parts and labour up as a sale by the signed-in user: parts leave stock, the sale gets a
    tax invoice number, and the ticket closes. Prices changed from the catalog count as approved by that user."""
    user = _user(principal)
    ticket = _ticket(db, ticket_id, principal.store_id)
    if ticket.ownership == "internal":
        raise ApiError(
            422,
            "internal_repair",
            "Shop equipment is a cost, not a customer sale. Record the parts against the ticket and do not invoice it.",
        )
    _editable(ticket)
    lines = list(
        db.scalars(select(RepairLine).where(RepairLine.ticket_id == ticket.id).order_by(RepairLine.created_at))
    )
    if not lines:
        raise ApiError(422, "nothing_to_invoice", "Add the parts and labour before invoicing.")
    policy = tax_policy_for(db)
    can_override = Permission.POS_PRICE_OVERRIDE.value in principal.permissions
    can_floor = Permission.POS_BELOW_FLOOR_OVERRIDE.value in principal.permissions
    approval = PriceOverridePayload(approved_by_id=user.id, note=f"Repair {_ref(ticket)}")
    items: list[SaleItemPayload] = []
    for line in lines:
        product = db.get(Product, line.product_id)
        if product is None:
            raise ApiError(422, "product_missing", f"{line.description} is no longer in the catalog.")
        taxed = line_tax(
            line.unit_price_cents,
            line.quantity,
            policy.rate_for(product.tax_category),
            inclusive=policy.prices_include_vat,
        )
        repriced = not product.is_open_price and line.unit_price_cents != product.price_cents
        if repriced and not can_override:
            raise ApiError(
                403, "price_override", f"{line.description} differs from the catalog price; a manager must invoice it."
            )
        items.append(
            SaleItemPayload(
                id=uuid.uuid4(),
                product_id=product.id,
                quantity=line.quantity,
                unit_price_cents=line.unit_price_cents,
                tax_cents=taxed.tax_cents,
                line_total_cents=taxed.line_total_cents,
                list_price_cents=None if product.is_open_price else product.price_cents,
                price_override=approval if repriced else None,
                description=line.description if product.is_open_price else None,
                below_floor_override=approval if can_floor and not product.is_open_price else None,
            )
        )
    total = sum(item.line_total_cents for item in items)
    tax = sum(item.tax_cents for item in items)
    held = sum(deposit.amount_cents for deposit in repair_workshop_service.held_deposits(db, ticket))
    if held > total:
        raise ApiError(
            409, "deposit_exceeds_total", "The deposit is more than the invoice; refund the difference first."
        )
    tenders = list(data.tenders) if data.tenders else None
    if tenders is None and total - held:
        tenders = [SaleTenderPayload(method=data.payment_method, amount_cents=total - held)]
    if held:
        tenders = [
            SaleTenderPayload(method="deposit", amount_cents=held, reference=f"Repair {_ref(ticket)}"),
            *(tenders or []),
        ]
    method = data.payment_method
    if tenders and all(tender.method != method for tender in tenders):
        method = tenders[-1].method
    sale_id = uuid.uuid4()
    repair_workshop_service.release_all(db, ticket)
    try:
        sale = record_sale(
            db,
            settings,
            SalePayload(
                id=sale_id,
                store_id=ticket.store_id,
                cashier_id=user.id,
                currency=ticket.currency,
                payment_method=method,
                subtotal_cents=total - tax,
                tax_cents=tax,
                total_cents=total,
                client_sale_id=str(sale_id),
                items=items,
                customer_id=ticket.customer_id,
                tenders=tenders,
            ),
            allow_deposit=bool(held),
        )
    except SyncRejected as exc:
        db.rollback()
        raise ApiError(422, "repair_invoice_rejected", exc.message) from exc
    except ValueError as exc:
        db.rollback()
        raise ApiError(422, "invalid_request", str(exc)) from exc
    ticket.sale_id = sale_id
    ticket.picked_up_at = datetime.now(UTC)
    repair_workshop_service.apply_deposits(db, ticket, sale_id)
    repair_workshop_service.create_repair_warranty(db, ticket, sale)
    credited = f", deposit {held / 100:.2f} credited" if held else ""
    _move(db, ticket, "closed", f"Invoiced {sale.invoice_number or str(sale_id)[:8].upper()}{credited}", user.id)
    db.commit()
    return detail(db, settings, ticket.id, principal.store_id)
