"""Repair workshop: status timeline, parts and labour on the ticket, and invoicing them as a normal sale."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.models.product import Product
from app.models.repair_ticket import RepairEvent, RepairLine, RepairTicket
from app.models.sale import Sale
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import PriceOverridePayload, SaleItemPayload, SalePayload, SaleTenderPayload
from app.schemas.repairs import (
    RepairDetail,
    RepairEventOut,
    RepairInvoiceCreate,
    RepairLineCreate,
    RepairLineOut,
    RepairStatusChange,
)
from app.services import repair_workshop_service
from app.services.catalog_service import get_repair
from app.services.sale_service import record_sale
from app.services.sync_service import notify_repair_ready
from app.services.tax import line_tax
from app.services.tax import policy as tax_policy_for

LABOUR_SKU = "SRV-REPAIR-LABOUR"
FINAL = ("closed", "cancelled")


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
    plain = RepairDetail(
        **base.model_dump(),
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
    enriched = repair_workshop_service.enrich(db, settings, ticket, plain)
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
