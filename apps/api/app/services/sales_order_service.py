"""Wholesale sales orders. An order is taken at the customer's price, confirmed (stock reserved, credit checked),
picked, and delivered in one or more deliveries. Each delivery is invoiced as it leaves: an ordinary sale through
record_sale (stock, IMEIs, costing, VAT, e-invoice and the customer ledger all follow from there). What cannot be
reserved yet is a backorder, allocated as stock arrives (goods receipts and a daily job)."""

import uuid
from collections import defaultdict
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError, SyncRejected
from app.core.pagination import count_rows
from app.core.permissions import Permission
from app.core.security import decrypt_value
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sales_order import DeliveryNote, DeliveryNoteLine, PickList, PickListLine, SalesOrder, SalesOrderLine
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.payloads import (
    CreditOverridePayload,
    PriceOverridePayload,
    SaleItemPayload,
    SalePayload,
    SaleTenderPayload,
)
from app.schemas.sales_orders import (
    BackorderRow,
    CancelLinesIn,
    ConfirmIn,
    DeliverIn,
    DeliveryNoteLineOut,
    DeliveryNoteOut,
    DispatchIn,
    PickListOut,
    SalesOrderCreate,
    SalesOrderLineIn,
    SalesOrderLineOut,
    SalesOrderOut,
    SalesOrderRow,
    SalesOrderUpdate,
)
from app.services import audit, inventory, price_list_service
from app.services.numbering import next_server_number
from app.services.sale_service import held_by_quote, record_sale
from app.services.tax import TaxPolicy, for_customer, line_tax
from app.services.tax import policy as tax_policy_for

OPEN_STATUSES = ("CONFIRMED", "PICKING", "PARTIALLY_DELIVERED")


def _now() -> datetime:
    return datetime.now(UTC)


def _rejected(exc: SyncRejected) -> ApiError:
    return ApiError(422, "rejected", str(exc))


def _tax_policy(db: Session, customer: Customer | None, store_id: uuid.UUID | None = None) -> TaxPolicy:
    return for_customer(tax_policy_for(db, store_id), customer, _now().date())


# --- Reading ----------------------------------------------------------------------------------------------


def _products(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, Product]:
    if not ids:
        return {}
    return {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(ids)))}


def _levels(db: Session, store_id: uuid.UUID, ids: set[uuid.UUID]) -> dict[uuid.UUID, InventoryLevel]:
    if not ids:
        return {}
    rows = db.scalars(
        select(InventoryLevel).where(InventoryLevel.store_id == store_id, InventoryLevel.product_id.in_(ids))
    ).all()
    return {row.product_id: row for row in rows}


def _delivery_out(db: Session, note: DeliveryNote, order: SalesOrder, customer_name: str) -> DeliveryNoteOut:
    products = _products(db, {line.product_id for line in note.lines})
    sale = db.get(Sale, note.sale_id) if note.sale_id else None
    driver = db.get(User, note.driver_id) if note.driver_id else None
    return DeliveryNoteOut(
        id=note.id,
        number=note.number,
        order_id=order.id,
        order_number=order.number,
        customer_name=customer_name,
        delivery_address=order.delivery_address,
        status=note.status,
        sale_id=note.sale_id,
        invoice_number=sale.invoice_number if sale else None,
        invoice_total_cents=sale.total_cents if sale else None,
        driver_name=driver.full_name if driver else None,
        vehicle=note.vehicle,
        dispatched_at=note.dispatched_at,
        delivered_at=note.delivered_at,
        receiver_name=note.receiver_name,
        has_signature=bool(note.signature),
        pod_note=note.pod_note,
        lines=[
            DeliveryNoteLineOut(
                order_line_id=line.order_line_id,
                product_id=line.product_id,
                product_name=products[line.product_id].name if line.product_id in products else "Item",
                quantity=line.quantity,
                serial_suffixes=list(line.serial_suffixes or []),
            )
            for line in note.lines
        ],
    )


def order_out(db: Session, order: SalesOrder) -> SalesOrderOut:
    customer = db.get(Customer, order.customer_id)
    ids = {line.product_id for line in order.lines}
    products = _products(db, ids)
    levels = _levels(db, order.store_id, ids)
    deliveries = db.scalars(
        select(DeliveryNote).where(DeliveryNote.order_id == order.id).order_by(DeliveryNote.dispatched_at)
    ).all()
    picks = db.scalars(select(PickList).where(PickList.order_id == order.id).order_by(PickList.created_at)).all()
    name = customer.name if customer else "Customer"
    delivered_cents = 0
    lines = []
    for line in order.lines:
        product = products.get(line.product_id)
        level = levels.get(line.product_id)
        if line.quantity_ordered:
            delivered_cents += line.line_total_cents * line.quantity_delivered // line.quantity_ordered
        lines.append(
            SalesOrderLineOut(
                id=line.id,
                product_id=line.product_id,
                product_name=product.name if product else "Removed product",
                sku=product.sku if product else "",
                is_serialized=bool(product and product.is_serialized),
                description=line.description,
                quantity_ordered=line.quantity_ordered,
                quantity_reserved=line.quantity_reserved,
                quantity_delivered=line.quantity_delivered,
                quantity_cancelled=line.quantity_cancelled,
                outstanding=line.outstanding,
                backordered=max(0, line.outstanding - line.quantity_reserved) if order.status in OPEN_STATUSES else 0,
                unit_price_cents=line.unit_price_cents,
                list_price_cents=line.list_price_cents,
                tax_cents=line.tax_cents,
                line_total_cents=line.line_total_cents,
                bin_location=level.aisle_shelf_location if level else None,
                available_now=max(0, level.available) if level else 0,
            )
        )
    return SalesOrderOut(
        id=order.id,
        number=order.number,
        store_id=order.store_id,
        customer_id=order.customer_id,
        customer_name=name,
        customer_type=customer.customer_type if customer else "RETAIL",
        status=order.status,  # type: ignore[arg-type]
        sale_type=order.sale_type,
        price_tier=order.price_tier,
        currency=order.currency,
        source=order.source,
        quote_id=order.quote_id,
        channel_ref=order.channel_ref,
        customer_reference=order.customer_reference,
        requested_date=order.requested_date,
        delivery_address=order.delivery_address,
        notes=order.notes,
        subtotal_cents=order.subtotal_cents,
        tax_cents=order.tax_cents,
        total_cents=order.total_cents,
        delivered_cents=delivered_cents,
        created_at=order.created_at,
        confirmed_at=order.confirmed_at,
        closed_at=order.closed_at,
        lines=lines,
        pick_lists=[
            PickListOut(
                id=pick.id,
                number=pick.number,
                status=pick.status,
                created_at=pick.created_at,
                lines=[
                    {
                        "order_line_id": str(item.order_line_id),
                        "product_id": str(item.product_id),
                        "product_name": products[item.product_id].name if item.product_id in products else "Item",
                        "quantity": item.quantity,
                        "bin_location": item.bin_location,
                    }
                    for item in pick.lines
                ],
            )
            for pick in picks
        ],
        deliveries=[_delivery_out(db, note, order, name) for note in deliveries],
    )


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(404, "not_found", "Sales order was not found.")


def _order(db: Session, principal: Principal, order_id: uuid.UUID, *, lock: bool = False) -> SalesOrder:
    order = db.get(SalesOrder, order_id, with_for_update=lock)
    if order is None:
        raise ApiError(404, "not_found", "Sales order was not found.")
    _scope(principal, order.store_id)
    return order


def get_order(db: Session, principal: Principal, order_id: uuid.UUID) -> SalesOrderOut:
    return order_out(db, _order(db, principal, order_id))


def list_orders(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID | None,
    status: str | None,
    customer_id: uuid.UUID | None,
    query: str | None,
    offset: int,
    limit: int,
) -> tuple[list[SalesOrderRow], int]:
    statement = select(SalesOrder, Customer.name).join(Customer, Customer.id == SalesOrder.customer_id)
    scope = principal.store_id or store_id
    if scope is not None:
        statement = statement.where(SalesOrder.store_id == scope)
    if status == "OPEN":
        statement = statement.where(SalesOrder.status.in_(OPEN_STATUSES))
    elif status:
        statement = statement.where(SalesOrder.status == status)
    if customer_id is not None:
        statement = statement.where(SalesOrder.customer_id == customer_id)
    if query:
        needle = f"%{query.strip().lower()}%"
        statement = statement.where(
            or_(
                func.lower(SalesOrder.number).like(needle),
                func.lower(Customer.name).like(needle),
                func.lower(func.coalesce(SalesOrder.customer_reference, "")).like(needle),
            )
        )
    total = count_rows(db, statement)
    rows = db.execute(statement.order_by(SalesOrder.created_at.desc()).offset(offset).limit(limit)).all()
    out = []
    for order, name in rows:
        open_ = order.status in OPEN_STATUSES
        out.append(
            SalesOrderRow(
                id=order.id,
                number=order.number,
                customer_name=name,
                status=order.status,  # type: ignore[arg-type]
                source=order.source,
                total_cents=order.total_cents,
                currency=order.currency,
                lines=len(order.lines),
                outstanding_units=sum(line.outstanding for line in order.lines) if open_ else 0,
                backordered_units=(
                    sum(max(0, line.outstanding - line.quantity_reserved) for line in order.lines) if open_ else 0
                ),
                requested_date=order.requested_date,
                created_at=order.created_at,
            )
        )
    return out, total


def backorders(db: Session, principal: Principal, store_id: uuid.UUID | None) -> list[BackorderRow]:
    statement = (
        select(SalesOrderLine, SalesOrder, Customer.name, Product)
        .join(SalesOrder, SalesOrder.id == SalesOrderLine.order_id)
        .join(Customer, Customer.id == SalesOrder.customer_id)
        .join(Product, Product.id == SalesOrderLine.product_id)
        .where(SalesOrder.status.in_(OPEN_STATUSES))
        .order_by(SalesOrder.confirmed_at, SalesOrderLine.position)
    )
    scope = principal.store_id or store_id
    if scope is not None:
        statement = statement.where(SalesOrder.store_id == scope)
    rows = []
    for line, order, name, product in db.execute(statement).all():
        waiting = line.outstanding - line.quantity_reserved
        if waiting <= 0:
            continue
        level = db.scalar(
            select(InventoryLevel).where(
                InventoryLevel.product_id == product.id, InventoryLevel.store_id == order.store_id
            )
        )
        rows.append(
            BackorderRow(
                order_id=order.id,
                order_number=order.number,
                customer_name=name,
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                backordered=waiting,
                available_now=max(0, level.available) if level else 0,
                requested_date=order.requested_date,
                ordered_at=order.confirmed_at or order.created_at,
            )
        )
    return rows


# --- Writing ----------------------------------------------------------------------------------------------


def _actor(db: Session, principal: Principal, user_id: uuid.UUID | None, *, allow_cashier: bool = False) -> User:
    """Registers call as the device for a cashier; portal users act as themselves."""
    user = principal.user if principal.user is not None else (db.get(User, user_id) if user_id else None)
    if user is None:
        raise ApiError(422, "invalid_request", "Name the user taking the order.")
    allowed = {Permission.SALES_ORDERS.value}
    if allow_cashier:
        allowed.add(Permission.POS_CREDIT_SALE.value)
    if not allowed & set(user.permissions):
        raise ApiError(403, "forbidden", f"{user.full_name} cannot take sales orders.")
    return user


def _approver(db: Session, approver_id: uuid.UUID | None, permission: Permission, label: str) -> User | None:
    if approver_id is None:
        return None
    approver = db.get(User, approver_id)
    if approver is None or permission.value not in approver.permissions:
        raise ApiError(403, "approval_required", f"The approving manager cannot approve the {label}.")
    return approver


def _price_lines(
    db: Session,
    order: SalesOrder,
    customer: Customer,
    lines: list[SalesOrderLineIn],
    price_approver: User | None,
) -> None:
    products = _products(db, {line.product_id for line in lines})
    pieces: dict[uuid.UUID, int] = defaultdict(int)
    for line in lines:
        pieces[line.product_id] += line.quantity
    tier = price_list_service.tier_for(order.sale_type, customer if order.sale_type == "WHOLESALE" else None, db)
    order.price_tier = tier
    policy = _tax_policy(db, customer, order.store_id)
    entries = price_list_service.entries_for(
        db, set(products), currency=order.currency, store_id=order.store_id, customer=customer
    )
    order.lines.clear()
    db.flush()
    subtotal = tax = total = 0
    for position, line in enumerate(lines):
        product = products.get(line.product_id)
        if product is None:
            raise ApiError(422, "invalid_request", "An ordered product does not exist.")
        if product.is_open_price or product.is_service or product.sold_by_weight:
            raise ApiError(422, "invalid_request", f"{product.name} is sold at the till, not on a sales order.")
        if getattr(product, "is_ingredient", False):
            raise ApiError(422, "invalid_request", f"{product.name} is an ingredient and is not sold on its own.")
        listed = price_list_service.resolve_for(
            product, tier, pieces[product.id], entries.get(product.id, []), customer=customer, store_id=order.store_id
        ).price_cents
        unit = listed if line.unit_price_cents is None else line.unit_price_cents
        if unit != listed and price_approver is None:
            raise ApiError(403, "approval_required", f"A manager must approve the price of {product.name}.")
        if policy.enforced:
            amounts = line_tax(
                unit, line.quantity, policy.rate_for(product.tax_category), inclusive=policy.prices_include_vat
            )
            net, line_tax_cents, line_total = amounts.net_cents, amounts.tax_cents, amounts.line_total_cents
        else:
            net, line_tax_cents, line_total = unit * line.quantity, 0, unit * line.quantity
        order.lines.append(
            SalesOrderLine(
                position=position,
                product_id=product.id,
                description=(line.description or "").strip() or None,
                quantity_ordered=line.quantity,
                unit_price_cents=unit,
                list_price_cents=listed,
                price_override_by_id=price_approver.id if unit != listed and price_approver else None,
                tax_cents=line_tax_cents,
                line_total_cents=line_total,
            )
        )
        subtotal += net
        tax += line_tax_cents
        total += line_total
    order.subtotal_cents, order.tax_cents, order.total_cents = subtotal, tax, total


def create_order(db: Session, principal: Principal, data: SalesOrderCreate) -> SalesOrderOut:
    _scope(principal, data.store_id)
    if data.id is not None and (existing := db.get(SalesOrder, data.id)) is not None:
        return order_out(db, existing)
    actor = _actor(db, principal, data.user_id, allow_cashier=True)
    store = db.get(Store, data.store_id)
    customer = db.get(Customer, data.customer_id)
    if store is None or customer is None:
        raise ApiError(404, "not_found", "Store or customer was not found.")
    order = SalesOrder(
        id=data.id or uuid.uuid4(),
        number=next_server_number(db, store.id, "SO"),
        store_id=store.id,
        customer_id=customer.id,
        status="DRAFT",
        sale_type=data.sale_type,
        currency=store.currency,
        source=data.source,
        channel_ref=data.channel_ref,
        customer_reference=(data.customer_reference or "").strip() or None,
        requested_date=data.requested_date,
        delivery_address=(data.delivery_address or customer.address or "").strip() or None,
        notes=(data.notes or "").strip(),
        created_by_id=actor.id,
    )
    db.add(order)
    price_approver = _approver(db, data.price_approved_by_id, Permission.POS_PRICE_OVERRIDE, "agreed prices")
    _price_lines(db, order, customer, data.lines, price_approver)
    db.flush()
    if data.confirm:
        _confirm(db, order, customer, actor, data.credit_approved_by_id)
    audit.record(
        db,
        action_type="CREATE",
        action="sales_order.create",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        new_values={"number": order.number, "total_cents": order.total_cents, "lines": len(order.lines)},
    )
    db.commit()
    return order_out(db, order)


def update_order(db: Session, principal: Principal, order_id: uuid.UUID, data: SalesOrderUpdate) -> SalesOrderOut:
    order = _order(db, principal, order_id, lock=True)
    _actor(db, principal, None)
    if data.lines is not None:
        if order.status != "DRAFT":
            raise ApiError(
                409, "order_confirmed", "Lines change only while the order is a draft; cancel lines instead."
            )
        customer = db.get(Customer, order.customer_id)
        assert customer is not None
        approver = _approver(db, data.price_approved_by_id, Permission.POS_PRICE_OVERRIDE, "agreed prices")
        _price_lines(db, order, customer, data.lines, approver)
    fields = data.model_fields_set
    if "requested_date" in fields:
        order.requested_date = data.requested_date
    if "delivery_address" in fields:
        order.delivery_address = (data.delivery_address or "").strip() or None
    if "customer_reference" in fields:
        order.customer_reference = (data.customer_reference or "").strip() or None
    if "notes" in fields:
        order.notes = (data.notes or "").strip()
    db.commit()
    return order_out(db, order)


def _exposure(db: Session, customer: Customer, except_order: uuid.UUID) -> int:
    """What the customer owes plus the undelivered value of their other open orders."""
    open_value = 0
    orders = db.scalars(
        select(SalesOrder).where(
            SalesOrder.customer_id == customer.id, SalesOrder.status.in_(OPEN_STATUSES), SalesOrder.id != except_order
        )
    ).all()
    for order in orders:
        for line in order.lines:
            if line.quantity_ordered:
                open_value += line.line_total_cents * line.outstanding // line.quantity_ordered
    return customer.current_balance_cents + open_value


def _confirm(
    db: Session, order: SalesOrder, customer: Customer, actor: User, credit_approver_id: uuid.UUID | None
) -> None:
    if order.status != "DRAFT":
        raise ApiError(409, "order_confirmed", "This order is already confirmed.")
    if customer.customer_type == "WHOLESALE" and customer.credit_limit_cents > 0:
        projected = _exposure(db, customer, order.id) + order.total_cents
        if projected > customer.credit_limit_cents:
            approver = _approver(db, credit_approver_id, Permission.CUSTOMERS_MANAGE, "credit limit")
            if approver is None:
                raise ApiError(
                    422,
                    "credit_limit",
                    f"{customer.name} would owe {projected / 100:.2f} against a limit of "
                    f"{customer.credit_limit_cents / 100:.2f}. A manager can approve it.",
                    details={"projected_cents": projected, "limit_cents": customer.credit_limit_cents},
                )
            audit.record(
                db,
                action_type="CREDIT_LIMIT_OVERRIDE",
                action="sales_order.credit_override",
                target_entity="SalesOrder",
                target_entity_id=order.id,
                store_id=order.store_id,
                user_id=actor.id,
                approver_id=approver.id,
                details={"projected_cents": projected, "limit_cents": customer.credit_limit_cents},
            )
    if customer.credit_hold and customer.customer_type == "WHOLESALE":
        approver = _approver(db, credit_approver_id, Permission.CUSTOMERS_MANAGE, "credit hold")
        if approver is None:
            raise ApiError(422, "credit_hold", f"{customer.name} is on credit hold: {customer.credit_hold_reason}.")
    order.status = "CONFIRMED"
    order.confirmed_at = _now()
    _reserve(db, order)


def _reserve(db: Session, order: SalesOrder) -> int:
    """Reserves what branch stock allows for each line; the rest waits as a backorder."""
    reserved = 0
    levels = _levels(db, order.store_id, {line.product_id for line in order.lines})
    for line in order.lines:
        wanted = line.outstanding - line.quantity_reserved
        if wanted <= 0:
            continue
        level = levels.get(line.product_id) or inventory.level_for(db, line.product_id, order.store_id)
        levels[line.product_id] = level
        take = min(wanted, max(0, level.available))
        if take > 0:
            inventory.reserve(db, line.product_id, order.store_id, take)
            line.quantity_reserved += take
            reserved += take
    db.flush()
    return reserved


def confirm(db: Session, principal: Principal, order_id: uuid.UUID, data: ConfirmIn) -> SalesOrderOut:
    order = _order(db, principal, order_id, lock=True)
    actor = _actor(db, principal, None)
    customer = db.get(Customer, order.customer_id)
    assert customer is not None
    _confirm(db, order, customer, actor, data.credit_approved_by_id)
    db.commit()
    return order_out(db, order)


def allocate(db: Session, principal: Principal, order_id: uuid.UUID) -> SalesOrderOut:
    order = _order(db, principal, order_id, lock=True)
    _actor(db, principal, None)
    if order.status not in OPEN_STATUSES:
        raise ApiError(409, "order_closed", "Only open orders take stock.")
    _reserve(db, order)
    db.commit()
    return order_out(db, order)


def allocate_store(db: Session, store_id: uuid.UUID) -> int:
    """Backorders take arriving stock first come, first served (by confirmation time). The caller commits."""
    orders = db.scalars(
        select(SalesOrder)
        .where(SalesOrder.store_id == store_id, SalesOrder.status.in_(OPEN_STATUSES))
        .order_by(SalesOrder.confirmed_at, SalesOrder.created_at)
    ).all()
    return sum(_reserve(db, order) for order in orders)


def allocate_all(db: Session) -> str:
    if not has_capability(db, Capability.SALES_ORDERS):
        return "sales orders are off"
    stores = db.scalars(select(SalesOrder.store_id).where(SalesOrder.status.in_(OPEN_STATUSES)).distinct()).all()
    units = sum(allocate_store(db, store_id) for store_id in stores)
    db.commit()
    return f"{units} backordered units allocated"


def pick_list(db: Session, principal: Principal, order_id: uuid.UUID) -> SalesOrderOut:
    """What to pull from the shelves now: every reserved, undelivered unit, with its bin."""
    order = _order(db, principal, order_id, lock=True)
    actor = _actor(db, principal, None)
    if order.status not in OPEN_STATUSES:
        raise ApiError(409, "order_closed", "Only open orders are picked.")
    levels = _levels(db, order.store_id, {line.product_id for line in order.lines})
    items = [
        PickListLine(
            order_line_id=line.id,
            product_id=line.product_id,
            quantity=min(line.quantity_reserved, line.outstanding),
            bin_location=levels[line.product_id].aisle_shelf_location if line.product_id in levels else None,
            position=position,
        )
        for position, line in enumerate(order.lines)
        if min(line.quantity_reserved, line.outstanding) > 0
    ]
    if not items:
        raise ApiError(422, "nothing_to_pick", "Nothing is reserved to pick yet; allocate stock first.")
    for previous in db.scalars(select(PickList).where(PickList.order_id == order.id, PickList.status == "OPEN")):
        previous.status = "REPLACED"
    items.sort(key=lambda item: (item.bin_location or "~", item.position))
    pick = PickList(
        number=next_server_number(db, order.store_id, "PCK"),
        order_id=order.id,
        store_id=order.store_id,
        status="OPEN",
        created_by_id=actor.id,
        lines=items,
    )
    db.add(pick)
    if order.status == "CONFIRMED":
        order.status = "PICKING"
    db.commit()
    return order_out(db, order)


def _serial_kind(value: str) -> str:
    digits = value.strip().replace(" ", "")
    return "imei" if digits.isdigit() and len(digits) == 15 else "serial"


def _free_serials(
    db: Session, settings: Settings, product: Product, store_id: uuid.UUID, count: int, taken: set[uuid.UUID]
) -> list[tuple[str, str]]:
    rows = db.scalars(
        select(SerialNumber)
        .where(
            SerialNumber.product_id == product.id,
            SerialNumber.store_id == store_id,
            SerialNumber.status == "in_stock",
        )
        .order_by(SerialNumber.created_at, SerialNumber.id)
    ).all()
    chosen: list[tuple[str, str]] = []
    for row in rows:
        if len(chosen) == count:
            break
        if row.id in taken or held_by_quote(db, row.id) is not None:
            continue
        taken.add(row.id)
        chosen.append((decrypt_value(row.value_encrypted, settings), row.kind))
    if len(chosen) < count:
        raise ApiError(422, "serials_short", f"Only {len(chosen)} {product.name} units are free to deliver.")
    return chosen


def _sale_item(
    order: SalesOrder,
    line: SalesOrderLine,
    product: Product,
    policy: TaxPolicy,
    quantity: int,
    serial: tuple[str, str] | None = None,
) -> SaleItemPayload:
    if policy.enforced:
        rate = policy.rate_for(product.tax_category)
        amounts = line_tax(line.unit_price_cents, quantity, rate, inclusive=policy.prices_include_vat)
        tax_cents, total_cents = amounts.tax_cents, amounts.line_total_cents
    else:
        tax_cents, total_cents = 0, line.unit_price_cents * quantity
    override = (
        PriceOverridePayload(approved_by_id=line.price_override_by_id, note=f"Agreed on {order.number}")
        if line.price_override_by_id is not None
        else None
    )
    return SaleItemPayload(
        id=uuid.uuid4(),
        product_id=product.id,
        quantity=quantity,
        unit_price_cents=line.unit_price_cents,
        list_price_cents=line.list_price_cents,
        price_override=override,
        tax_cents=tax_cents,
        line_total_cents=total_cents,
        description=line.description,
        serial_value=serial[0] if serial else None,
        serial_kind=serial[1] if serial else None,  # type: ignore[arg-type]
    )


def dispatch(
    db: Session, settings: Settings, principal: Principal, order_id: uuid.UUID, data: DispatchIn
) -> SalesOrderOut:
    """Ships part or all of the order and invoices exactly what left."""
    order = _order(db, principal, order_id, lock=True)
    actor = _actor(db, principal, None)
    if order.status not in OPEN_STATUSES:
        raise ApiError(409, "order_closed", "Only open orders are delivered.")
    customer = db.get(Customer, order.customer_id)
    assert customer is not None
    lines = {line.id: line for line in order.lines}
    products = _products(db, {line.product_id for line in order.lines})
    policy = _tax_policy(db, customer, order.store_id)
    sale_id = uuid.uuid4()
    items: list[SaleItemPayload] = []
    line_of_item: dict[uuid.UUID, uuid.UUID] = {}
    note_lines: list[DeliveryNoteLine] = []
    taken: set[uuid.UUID] = set()
    seen: set[uuid.UUID] = set()
    for position, entry in enumerate(data.lines):
        line = lines.get(entry.order_line_id)
        if line is None or line.id in seen:
            raise ApiError(422, "invalid_request", "Each delivery line must be a different line of this order.")
        seen.add(line.id)
        if entry.quantity > line.outstanding:
            raise ApiError(422, "over_delivery", f"Only {line.outstanding} left to deliver on this line.")
        product = products[line.product_id]
        suffixes: list[str] = []
        if product.is_serialized:
            if entry.serials and len(entry.serials) != entry.quantity:
                raise ApiError(422, "serials_required", f"Scan {entry.quantity} IMEIs for {product.name}.")
            serials = (
                [(value.strip(), _serial_kind(value)) for value in entry.serials]
                if entry.serials
                else _free_serials(db, settings, product, order.store_id, entry.quantity, taken)
            )
            for serial in serials:
                sale_item = _sale_item(order, line, product, policy, 1, serial)
                items.append(sale_item)
                line_of_item[sale_item.id] = line.id
                suffixes.append(serial[0][-4:])
        else:
            sale_item = _sale_item(order, line, product, policy, entry.quantity)
            items.append(sale_item)
            line_of_item[sale_item.id] = line.id
        note_lines.append(
            DeliveryNoteLine(
                order_line_id=line.id,
                product_id=product.id,
                quantity=entry.quantity,
                serial_suffixes=suffixes or None,
                position=position,
            )
        )
        # The order's hold on these units ends as they leave, so the sale can take them.
        released = min(line.quantity_reserved, entry.quantity)
        if released:
            inventory.release(db, product.id, order.store_id, released)
            line.quantity_reserved -= released
        line.quantity_delivered += entry.quantity

    total = sum(entry.line_total_cents for entry in items)
    tax = sum(entry.tax_cents for entry in items)
    tenders = list(data.tenders) if data.tenders else None
    method = data.payment_method
    if tenders is None:
        if method is None and customer.customer_type == "WHOLESALE":
            method = "on_account"
        if method is None:
            raise ApiError(422, "payment_required", "Take payment for this delivery, or invoice a wholesale account.")
        tenders = [SaleTenderPayload(method=method, amount_cents=total)] if total else None
    else:
        method = method or tenders[-1].method
    payload = SalePayload(
        id=sale_id,
        store_id=order.store_id,
        cashier_id=actor.id,
        currency=order.currency,
        payment_method=method,  # type: ignore[arg-type]
        subtotal_cents=total - tax,
        tax_cents=tax,
        total_cents=total,
        client_sale_id=str(sale_id),
        items=items,
        sale_type=order.sale_type,  # type: ignore[arg-type]
        customer_id=customer.id,
        tenders=tenders,
        credit_override=(
            CreditOverridePayload(approved_by_id=data.credit_approved_by_id, note=f"Delivery of {order.number}")
            if data.credit_approved_by_id
            else None
        ),
    )
    try:
        sale = record_sale(db, settings, payload)
    except SyncRejected as exc:
        db.rollback()
        raise _rejected(exc) from exc
    except ValueError as exc:
        db.rollback()
        raise ApiError(422, "invalid_request", str(exc)) from exc
    sale.sales_order_id = order.id
    for sale_item in db.scalars(select(SaleItem).where(SaleItem.sale_id == sale.id)):
        sale_item.sales_order_line_id = line_of_item.get(sale_item.id)
    note = DeliveryNote(
        number=next_server_number(db, order.store_id, "DN"),
        order_id=order.id,
        store_id=order.store_id,
        status="DISPATCHED",
        sale_id=sale.id,
        driver_id=data.driver_id,
        vehicle=(data.vehicle or "").strip() or None,
        dispatched_by_id=actor.id,
        dispatched_at=_now(),
        lines=note_lines,
    )
    db.add(note)
    for pick in db.scalars(select(PickList).where(PickList.order_id == order.id, PickList.status == "OPEN")):
        pick.status = "DONE"
    _refresh_status(order)
    audit.record(
        db,
        action_type="UPDATE",
        action="sales_order.dispatch",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"delivery": note.number, "invoice": sale.invoice_number, "total_cents": total},
    )
    db.commit()
    return order_out(db, order)


def _refresh_status(order: SalesOrder) -> None:
    if order.status in ("DRAFT", "CLOSED", "CANCELLED"):
        return
    if all(line.outstanding == 0 for line in order.lines):
        delivered = any(line.quantity_delivered for line in order.lines)
        order.status = "DELIVERED" if delivered else "CANCELLED"
        order.closed_at = _now()
    elif any(line.quantity_delivered for line in order.lines):
        order.status = "PARTIALLY_DELIVERED"


def _note(db: Session, principal: Principal, note_id: uuid.UUID) -> tuple[DeliveryNote, SalesOrder]:
    note = db.get(DeliveryNote, note_id)
    if note is None:
        raise ApiError(404, "not_found", "Delivery note was not found.")
    order = _order(db, principal, note.order_id)
    return note, order


def delivery(db: Session, principal: Principal, note_id: uuid.UUID) -> DeliveryNoteOut:
    note, order = _note(db, principal, note_id)
    customer = db.get(Customer, order.customer_id)
    return _delivery_out(db, note, order, customer.name if customer else "Customer")


def deliver(db: Session, principal: Principal, note_id: uuid.UUID, data: DeliverIn) -> DeliveryNoteOut:
    """Proof of delivery: who received it, their signature, and when."""
    note, order = _note(db, principal, note_id)
    actor = _actor(db, principal, None)
    if note.status == "DELIVERED":
        raise ApiError(409, "already_delivered", "This delivery is already signed for.")
    note.status = "DELIVERED"
    note.delivered_at = _now()
    note.receiver_name = data.receiver_name.strip()
    note.signature = data.signature
    note.pod_note = (data.note or "").strip() or None
    audit.record(
        db,
        action_type="UPDATE",
        action="sales_order.delivered",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"delivery": note.number, "receiver": note.receiver_name},
    )
    db.commit()
    customer = db.get(Customer, order.customer_id)
    return _delivery_out(db, note, order, customer.name if customer else "Customer")


def cancel_lines(db: Session, principal: Principal, order_id: uuid.UUID, data: CancelLinesIn) -> SalesOrderOut:
    order = _order(db, principal, order_id, lock=True)
    actor = _actor(db, principal, None)
    if order.status in ("CLOSED", "CANCELLED", "DELIVERED"):
        raise ApiError(409, "order_closed", "This order is closed.")
    lines = {line.id: line for line in order.lines}
    for entry in data.lines:
        line = lines.get(entry.order_line_id)
        if line is None:
            raise ApiError(422, "invalid_request", "That line is not on this order.")
        if entry.quantity > line.outstanding:
            raise ApiError(422, "invalid_request", f"Only {line.outstanding} left to cancel on this line.")
        line.quantity_cancelled += entry.quantity
        excess = line.quantity_reserved - line.outstanding
        if excess > 0:
            inventory.release(db, line.product_id, order.store_id, excess)
            line.quantity_reserved -= excess
    audit.record(
        db,
        action_type="UPDATE",
        action="sales_order.cancel_lines",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        reason_notes=data.reason,
        details={"lines": [{"line": str(entry.order_line_id), "quantity": entry.quantity} for entry in data.lines]},
    )
    if order.status != "DRAFT":
        _refresh_status(order)
    db.commit()
    return order_out(db, order)


def _finish(db: Session, principal: Principal, order_id: uuid.UUID, reason: str, status: str) -> SalesOrderOut:
    """Cancels (nothing delivered yet) or closes (short-ships) the order, releasing every reservation."""
    order = _order(db, principal, order_id, lock=True)
    actor = _actor(db, principal, None)
    if order.status in ("CLOSED", "CANCELLED", "DELIVERED"):
        raise ApiError(409, "order_closed", "This order is already closed.")
    delivered = any(line.quantity_delivered for line in order.lines)
    if status == "CANCELLED" and delivered:
        raise ApiError(409, "already_delivered", "Part of this order was delivered; close it instead.")
    for line in order.lines:
        if line.quantity_reserved:
            inventory.release(db, line.product_id, order.store_id, line.quantity_reserved)
            line.quantity_reserved = 0
        line.quantity_cancelled += line.outstanding
    order.status = status
    order.closed_at = _now()
    audit.record(
        db,
        action_type="UPDATE",
        action=f"sales_order.{status.lower()}",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        reason_notes=reason,
    )
    db.commit()
    return order_out(db, order)


def cancel_order(db: Session, principal: Principal, order_id: uuid.UUID, reason: str) -> SalesOrderOut:
    return _finish(db, principal, order_id, reason, "CANCELLED")


def close_order(db: Session, principal: Principal, order_id: uuid.UUID, reason: str) -> SalesOrderOut:
    return _finish(db, principal, order_id, reason, "CLOSED")


def from_quote(db: Session, principal: Principal, quote_id: uuid.UUID) -> SalesOrderOut:
    """Moves an open quote's lines and stock hold onto a confirmed sales order (to deliver in parts)."""
    from app.services import quote_service

    quote = db.get(Sale, quote_id)
    if quote is None or not quote.is_quote_proforma:
        raise ApiError(404, "not_found", "Quote was not found.")
    _scope(principal, quote.store_id)
    actor = _actor(db, principal, None)
    if quote.quote_status != "OPEN":
        raise ApiError(422, "quote_closed", f"This quote is already {str(quote.quote_status).lower()}.")
    if quote.customer_id is None:
        raise ApiError(422, "invalid_request", "Attach a customer to the quote first.")
    if quote_service._active_deposits(db, quote.id):
        raise ApiError(422, "has_deposits", "This quote holds deposits; convert it to a sale to apply them.")
    grouped: dict[tuple[uuid.UUID, int, int, uuid.UUID | None], int] = defaultdict(int)
    for item in quote.items:
        key = (
            item.product_id,
            item.unit_price_cents,
            item.list_price_cents or item.unit_price_cents,
            item.price_override_by_id,
        )
        grouped[key] += item.quantity
    store = db.get(Store, quote.store_id)
    assert store is not None
    order = SalesOrder(
        number=next_server_number(db, store.id, "SO"),
        store_id=store.id,
        customer_id=quote.customer_id,
        status="CONFIRMED",
        sale_type=quote.sale_type,
        currency=quote.currency,
        source="quote",
        quote_id=quote.id,
        created_by_id=actor.id,
        confirmed_at=_now(),
    )
    customer = db.get(Customer, quote.customer_id)
    order.price_tier = price_list_service.tier_for(quote.sale_type, customer, db)
    policy = _tax_policy(db, customer, order.store_id)
    products = _products(db, {key[0] for key in grouped})
    subtotal = tax = total = 0
    for position, ((product_id, unit, listed, approver), quantity) in enumerate(grouped.items()):
        product = products[product_id]
        if policy.enforced:
            amounts = line_tax(
                unit, quantity, policy.rate_for(product.tax_category), inclusive=policy.prices_include_vat
            )
            net, line_tax_cents, line_total = amounts.net_cents, amounts.tax_cents, amounts.line_total_cents
        else:
            net, line_tax_cents, line_total = unit * quantity, 0, unit * quantity
        order.lines.append(
            SalesOrderLine(
                position=position,
                product_id=product_id,
                quantity_ordered=quantity,
                unit_price_cents=unit,
                list_price_cents=listed,
                price_override_by_id=approver,
                tax_cents=line_tax_cents,
                line_total_cents=line_total,
            )
        )
        subtotal, tax, total = subtotal + net, tax + line_tax_cents, total + line_total
    order.subtotal_cents, order.tax_cents, order.total_cents = subtotal, tax, total
    db.add(order)
    quote_service._release(db, quote)
    quote.quote_status = "CONVERTED"
    db.flush()
    _reserve(db, order)
    audit.record(
        db,
        action_type="CREATE",
        action="sales_order.from_quote",
        target_entity="SalesOrder",
        target_entity_id=order.id,
        store_id=order.store_id,
        user_id=actor.id,
        details={"quote": quote.invoice_number, "order": order.number},
    )
    db.commit()
    return order_out(db, order)
