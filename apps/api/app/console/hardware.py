"""Optional hardware catalogue. Lease rent, deposits, fees, and purchases are priced separately.

A tenant chooses quantities per store. Paying the invoice records the order as awaiting fulfillment.
It does not deliver the hardware or refund the deposit.
"""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.console.security import OperatorPrincipal, audit_operator
from app.core.errors import ApiError
from app.schemas.billing import QuoteLine
from app.schemas.hardware import (
    DepositDecisionIn,
    EcAssignIn,
    EcDeviceOut,
    EcReadinessOut,
    EcRegisterIn,
    FulfillmentIn,
    HardwareAssignmentOut,
    HardwareCategoryIn,
    HardwareCategoryOut,
    HardwareItemIn,
    HardwareItemOut,
    HardwareLineOut,
    HardwareOrderOut,
    HardwarePick,
)
from app.tenancy.models import (
    HardwareAssignment,
    HardwareCategory,
    HardwareItem,
    HardwareOrder,
    HardwareOrderLine,
    Tenant,
)

log = logging.getLogger(__name__)

_CATEGORIES = (
    "POS terminals",
    "Touchscreen monitors",
    "Receipt printers",
    "Barcode scanners",
    "Cash drawers",
    "Customer displays",
    "Kitchen display systems",
    "Kitchen printers",
    "Network equipment",
    "Tablets",
    "Payment terminals",
    "Other",
)


def ensure_categories(db: Session) -> None:
    if db.scalar(select(HardwareCategory.id).limit(1)) is not None:
        return
    for index, name in enumerate(_CATEGORIES):
        db.add(HardwareCategory(name=name, sort_order=index, active=True))
    db.flush()


def _category(db: Session, category_id: uuid.UUID) -> HardwareCategory:
    row = db.get(HardwareCategory, category_id)
    if row is None or not row.active:
        raise ApiError(422, "unknown_category", "Choose an active hardware category.")
    return row


def _item_out(
    row: HardwareItem, category_name: str, *, now: datetime | None = None, include_notes: bool = False
) -> HardwareItemOut:
    moment = now or datetime.now(UTC)
    in_window = (row.effective_from is None or row.effective_from <= moment) and (
        row.effective_to is None or row.effective_to >= moment
    )
    in_stock = row.stock_qty is None or row.stock_qty > 0
    offered = row.lease_available or row.purchase_available
    available = row.active and not row.archived and in_window and in_stock and offered
    return HardwareItemOut(
        id=row.id,
        sku=row.sku,
        name=row.name,
        category_id=row.category_id,
        category_name=category_name,
        description=row.description,
        image_url=row.image_url,
        manufacturer=row.manufacturer,
        model=row.model,
        lease_available=row.lease_available,
        purchase_available=row.purchase_available,
        monthly_fils=row.monthly_fils,
        deposit_fils=row.deposit_fils,
        fee_fils=row.fee_fils,
        purchase_fils=row.purchase_fils,
        delivery_fils=row.delivery_fils,
        currency=row.currency,
        min_qty=row.min_qty,
        max_qty=row.max_qty,
        stock_qty=row.stock_qty,
        counts_as_register=row.counts_as_register,
        compatibility=row.compatibility,
        device_type=row.device_type or "",
        warranty_months=row.warranty_months or 0,
        specifications=dict(row.specifications or {}),
        installation_fils=row.installation_fils or 0,
        active=row.active,
        archived=row.archived,
        available=available,
        internal_notes=row.internal_notes if include_notes else "",
    )


def list_ec_items(db: Session) -> list[HardwareItemOut]:
    """Published wired and Android terminals. Other hardware stays on the general catalogue."""
    return [
        row
        for row in list_items(db, sellable_only=True)
        if row.device_type in {"WIRED", "ANDROID"} and row.purchase_available
    ]


def list_items(db: Session, *, sellable_only: bool = False, include_notes: bool = False) -> list[HardwareItemOut]:
    ensure_categories(db)
    names = {row.id: row.name for row in db.scalars(select(HardwareCategory))}
    rows = list(db.scalars(select(HardwareItem).order_by(HardwareItem.name)))
    found = [_item_out(row, names.get(row.category_id, ""), include_notes=include_notes) for row in rows]
    if sellable_only:
        return [row for row in found if row.available]
    return found


def list_categories(db: Session) -> list[HardwareCategoryOut]:
    ensure_categories(db)
    rows = db.scalars(select(HardwareCategory).order_by(HardwareCategory.sort_order, HardwareCategory.name))
    return [HardwareCategoryOut(id=row.id, name=row.name, sort_order=row.sort_order, active=row.active) for row in rows]


def _check_item(data: HardwareItemIn) -> None:
    if not data.lease_available and not data.purchase_available:
        raise ApiError(422, "hardware_mode", "Offer the item for lease, purchase, or both.")
    if data.purchase_available and data.purchase_fils is None:
        raise ApiError(422, "purchase_price", "A purchase item needs a purchase price.")
    if data.max_qty < data.min_qty:
        raise ApiError(422, "quantity_range", "The maximum quantity cannot be below the minimum.")
    if data.currency.upper() != "AED":
        raise ApiError(422, "currency", "Hardware prices are in AED.")
    if data.device_type in {"WIRED", "ANDROID"} and not data.purchase_available:
        raise ApiError(422, "purchase_price", "An EC machine is sold, not bundled into the subscription.")
    if data.specifications and not isinstance(data.specifications, dict):
        raise ApiError(422, "specifications", "Specifications must be a set of named values.")


def create_item(db: Session, operator: OperatorPrincipal, data: HardwareItemIn) -> HardwareItemOut:
    ensure_categories(db)
    _check_item(data)
    category = _category(db, data.category_id)
    sku = data.sku.strip().upper()
    if db.scalar(select(HardwareItem.id).where(HardwareItem.sku == sku)) is not None:
        raise ApiError(409, "duplicate_sku", "That SKU is already in the catalogue.")
    row = HardwareItem(
        sku=sku,
        name=data.name.strip(),
        category_id=category.id,
        description=data.description.strip(),
        image_url=(data.image_url or "").strip() or None,
        manufacturer=data.manufacturer.strip(),
        model=data.model.strip(),
        lease_available=data.lease_available,
        purchase_available=data.purchase_available,
        monthly_fils=data.monthly_fils,
        deposit_fils=data.deposit_fils if data.lease_available else 0,
        fee_fils=data.fee_fils,
        purchase_fils=data.purchase_fils if data.purchase_available else None,
        delivery_fils=data.delivery_fils,
        currency="AED",
        min_qty=data.min_qty,
        max_qty=data.max_qty,
        stock_qty=data.stock_qty,
        counts_as_register=data.counts_as_register,
        compatibility=data.compatibility.strip(),
        device_type=data.device_type,
        warranty_months=data.warranty_months,
        specifications=dict(data.specifications or {}),
        installation_fils=data.installation_fils,
        active=data.active,
        archived=data.archived,
        effective_from=data.effective_from,
        effective_to=data.effective_to,
        internal_notes=data.internal_notes.strip(),
    )
    db.add(row)
    db.flush()
    audit_operator(db, operator, "hardware.item.create", after={"sku": sku, "name": row.name}, reason=data.reason)
    db.commit()
    return _item_out(row, category.name, include_notes=True)


def update_item(db: Session, operator: OperatorPrincipal, item_id: uuid.UUID, data: HardwareItemIn) -> HardwareItemOut:
    row = db.get(HardwareItem, item_id)
    if row is None:
        raise ApiError(404, "not_found", "That hardware item does not exist.")
    _check_item(data)
    category = _category(db, data.category_id)
    before = {"sku": row.sku, "monthly_fils": row.monthly_fils, "deposit_fils": row.deposit_fils, "active": row.active}
    row.name = data.name.strip()
    row.category_id = category.id
    row.description = data.description.strip()
    row.image_url = (data.image_url or "").strip() or None
    row.manufacturer = data.manufacturer.strip()
    row.model = data.model.strip()
    row.lease_available = data.lease_available
    row.purchase_available = data.purchase_available
    row.monthly_fils = data.monthly_fils
    row.deposit_fils = data.deposit_fils if data.lease_available else 0
    row.fee_fils = data.fee_fils
    row.purchase_fils = data.purchase_fils if data.purchase_available else None
    row.delivery_fils = data.delivery_fils
    row.min_qty = data.min_qty
    row.max_qty = data.max_qty
    row.stock_qty = data.stock_qty
    row.counts_as_register = data.counts_as_register
    row.compatibility = data.compatibility.strip()
    row.device_type = data.device_type
    row.warranty_months = data.warranty_months
    row.specifications = dict(data.specifications or {})
    row.installation_fils = data.installation_fils
    row.active = data.active
    row.archived = data.archived
    row.effective_from = data.effective_from
    row.effective_to = data.effective_to
    row.internal_notes = data.internal_notes.strip()
    row.updated_at = datetime.now(UTC)
    audit_operator(
        db,
        operator,
        "hardware.item.update",
        before=before,
        after={"monthly_fils": row.monthly_fils, "deposit_fils": row.deposit_fils, "active": row.active},
        reason=data.reason,
    )
    db.commit()
    return _item_out(row, category.name, include_notes=True)


def update_category(
    db: Session, operator: OperatorPrincipal, category_id: uuid.UUID, data: HardwareCategoryIn
) -> HardwareCategoryOut:
    ensure_categories(db)
    row = db.get(HardwareCategory, category_id)
    if row is None:
        raise ApiError(404, "not_found", "Category was not found.")
    name = data.name.strip()
    clash = db.scalar(
        select(HardwareCategory.id).where(HardwareCategory.name == name, HardwareCategory.id != row.id)
    )
    if clash is not None:
        raise ApiError(409, "duplicate_category", "That category already exists.")
    before = {"name": row.name, "active": row.active}
    row.name = name
    row.sort_order = data.sort_order
    row.active = data.active
    audit_operator(
        db,
        operator,
        "hardware.category.update",
        before=before,
        after={"name": name, "active": row.active},
        reason=data.reason,
    )
    db.commit()
    return HardwareCategoryOut(id=row.id, name=row.name, sort_order=row.sort_order, active=row.active)


def create_category(db: Session, operator: OperatorPrincipal, data: HardwareCategoryIn) -> HardwareCategoryOut:
    ensure_categories(db)
    name = data.name.strip()
    if db.scalar(select(HardwareCategory.id).where(HardwareCategory.name == name)) is not None:
        raise ApiError(409, "duplicate_category", "That category already exists.")
    row = HardwareCategory(name=name, sort_order=data.sort_order, active=data.active)
    db.add(row)
    db.flush()
    audit_operator(db, operator, "hardware.category.create", after={"name": name}, reason=data.reason)
    db.commit()
    return HardwareCategoryOut(id=row.id, name=row.name, sort_order=row.sort_order, active=row.active)


def price_selection(
    db: Session,
    picks: list[HardwarePick],
    *,
    months: int,
    discount_bps: int,
    included_registers: int,
    stores: dict[uuid.UUID, str] | None,
) -> tuple[list[QuoteLine], int, int]:
    """Invoice lines, the monthly lease (not multiplied by the cycle), and the refundable deposit."""
    from app.console.billing import cycle_amount

    if not picks:
        return [], 0, 0
    lines: list[QuoteLine] = []
    monthly = 0
    deposit = 0
    registers = 0
    used: dict[uuid.UUID, int] = {}
    seen: set[tuple[uuid.UUID, str, uuid.UUID | None, str]] = set()
    for index, pick in enumerate(picks):
        item = db.get(HardwareItem, pick.item_id)
        if item is None:
            raise ApiError(422, "unknown_hardware", "One of the hardware items is not in the catalogue.")
        shown = _item_out(item, "")
        if not shown.available:
            raise ApiError(422, "hardware_unavailable", f"{item.name} is not available. Choose another item.")
        if pick.mode == "lease" and not item.lease_available:
            raise ApiError(422, "lease_unavailable", f"{item.name} is not offered for lease.")
        if pick.mode == "purchase" and not item.purchase_available:
            raise ApiError(422, "purchase_unavailable", f"{item.name} is not offered for purchase.")
        if pick.quantity < item.min_qty or pick.quantity > item.max_qty:
            raise ApiError(422, "quantity", f"Order {item.name} between {item.min_qty} and {item.max_qty}.")
        used[item.id] = used.get(item.id, 0) + pick.quantity
        if item.stock_qty is not None and used[item.id] > item.stock_qty:
            raise ApiError(422, "stock", f"Only {item.stock_qty} of {item.name} are available.")
        label = pick.store_label.strip()
        if pick.store_id is not None:
            if stores is not None and pick.store_id not in stores:
                raise ApiError(422, "unknown_store", "Assign hardware only to a store this business owns.")
            if stores is not None:
                label = stores[pick.store_id]
            elif label == "":
                label = "Store"
        elif label == "":
            raise ApiError(422, "store_required", "Name the store this hardware is for, or choose one of your stores.")
        key = (item.id, pick.mode, pick.store_id, label.casefold())
        if key in seen:
            raise ApiError(
                422, "duplicate_hardware", f"{item.name} is already selected for {label}. Change the quantity."
            )
        seen.add(key)
        place = f" · {label}"
        if pick.mode == "lease":
            unit = cycle_amount(item.monthly_fils, months, discount_bps)
            lines.append(
                QuoteLine(
                    code=f"h{index}m",
                    label=f"{item.name} lease{place}",
                    quantity=pick.quantity,
                    unit_fils=unit,
                    amount_fils=unit * pick.quantity,
                    recurring=True,
                    refundable=False,
                )
            )
            monthly += item.monthly_fils * pick.quantity
            if item.deposit_fils:
                lines.append(
                    QuoteLine(
                        code=f"h{index}d",
                        label=f"{item.name} refundable deposit{place}",
                        quantity=pick.quantity,
                        unit_fils=item.deposit_fils,
                        amount_fils=item.deposit_fils * pick.quantity,
                        recurring=False,
                        refundable=True,
                    )
                )
                deposit += item.deposit_fils * pick.quantity
        else:
            price = item.purchase_fils or 0
            lines.append(
                QuoteLine(
                    code=f"h{index}p",
                    label=f"{item.name} purchase{place}",
                    quantity=pick.quantity,
                    unit_fils=price,
                    amount_fils=price * pick.quantity,
                    recurring=False,
                    refundable=False,
                )
            )
        if item.fee_fils:
            lines.append(
                QuoteLine(
                    code=f"h{index}f",
                    label=f"{item.name} fee{place}",
                    quantity=pick.quantity,
                    unit_fils=item.fee_fils,
                    amount_fils=item.fee_fils * pick.quantity,
                    recurring=False,
                    refundable=False,
                )
            )
        if item.delivery_fils:
            lines.append(
                QuoteLine(
                    code=f"h{index}v",
                    label=f"{item.name} delivery{place}",
                    quantity=pick.quantity,
                    unit_fils=item.delivery_fils,
                    amount_fils=item.delivery_fils * pick.quantity,
                    recurring=False,
                    refundable=False,
                )
            )
        if item.installation_fils:
            lines.append(
                QuoteLine(
                    code=f"h{index}i",
                    label=f"{item.name} installation{place}",
                    quantity=pick.quantity,
                    unit_fils=item.installation_fils,
                    amount_fils=item.installation_fils * pick.quantity,
                    recurring=False,
                    refundable=False,
                )
            )
        if item.counts_as_register:
            registers += pick.quantity
    if registers > included_registers:
        raise ApiError(
            422,
            "register_limit",
            f"This package includes {included_registers} registers. "
            f"The hardware selection needs {registers}. Choose a larger package or fewer terminals. "
            "The package was not changed.",
        )
    return lines, monthly, deposit


def _reference(db: Session) -> str:
    stem = datetime.now(UTC).strftime("HW%y%m")
    for offset in range(1, 100):
        candidate = f"{stem}-{offset:04d}"
        if db.scalar(select(HardwareOrder.id).where(HardwareOrder.reference == candidate)) is None:
            return candidate
    raise ApiError(409, "reference", "Could not allocate a hardware order number.")


def open_order(
    db: Session,
    *,
    tenant_id: uuid.UUID,
    invoice_id: uuid.UUID,
    picks: list[HardwarePick],
    stores: dict[uuid.UUID, str] | None,
) -> HardwareOrder | None:
    if not picks:
        return None
    locked = db.scalar(
        select(HardwareOrder.id).where(
            HardwareOrder.tenant_id == tenant_id,
            HardwareOrder.payment_status == "under_review",
        )
    )
    if locked is not None:
        raise ApiError(
            409,
            "hardware_locked",
            "A hardware order is under payment review. Wait for a decision before changing it.",
        )
    previous = db.scalars(
        select(HardwareOrder).where(
            HardwareOrder.tenant_id == tenant_id,
            HardwareOrder.payment_status == "awaiting_payment",
        )
    )
    for order in previous:
        order.payment_status = "canceled"
        order.fulfillment_status = "canceled"
    row = HardwareOrder(reference=_reference(db), tenant_id=tenant_id, invoice_id=invoice_id)
    db.add(row)
    db.flush()
    monthly = 0
    deposit = 0
    once = 0
    for pick in picks:
        item = db.get(HardwareItem, pick.item_id)
        if item is None:
            raise ApiError(422, "unknown_hardware", "One of the hardware items is not in the catalogue.")
        label = pick.store_label.strip()
        if pick.store_id and stores:
            label = stores.get(pick.store_id, label)
        line_monthly = item.monthly_fils if pick.mode == "lease" else 0
        line_deposit = item.deposit_fils if pick.mode == "lease" else 0
        line_purchase = (item.purchase_fils or 0) if pick.mode == "purchase" else 0
        db.add(
            HardwareOrderLine(
                order_id=row.id,
                item_id=item.id,
                sku=item.sku,
                name=item.name,
                store_id=pick.store_id,
                store_label=label,
                mode=pick.mode,
                quantity=pick.quantity,
                monthly_fils=line_monthly,
                deposit_fils=line_deposit,
                fee_fils=item.fee_fils,
                purchase_fils=line_purchase,
                delivery_fils=item.delivery_fils,
                device_type=item.device_type or "",
                warranty_months=item.warranty_months or 0,
                installation_fils=item.installation_fils or 0,
                serials=[],
            )
        )
        monthly += line_monthly * pick.quantity
        deposit += line_deposit * pick.quantity
        once += (item.fee_fils + line_purchase + item.delivery_fils + (item.installation_fils or 0)) * pick.quantity
    row.monthly_fils = monthly
    row.deposit_fils = deposit
    row.one_time_fils = once
    return row


def _order_for_invoice(db: Session, invoice_id: uuid.UUID) -> HardwareOrder | None:
    return db.scalar(select(HardwareOrder).where(HardwareOrder.invoice_id == invoice_id))


def mark_under_review(db: Session, invoice_id: uuid.UUID) -> None:
    order = _order_for_invoice(db, invoice_id)
    if order is None or order.payment_status != "awaiting_payment":
        return
    order.payment_status = "under_review"
    order.fulfillment_status = "under_review"
    order.updated_at = datetime.now(UTC)


def release_review(db: Session, invoice_id: uuid.UUID) -> None:
    order = _order_for_invoice(db, invoice_id)
    if order is None or order.payment_status != "under_review":
        return
    order.payment_status = "awaiting_payment"
    order.fulfillment_status = "awaiting_payment"
    order.updated_at = datetime.now(UTC)


def mark_paid(db: Session, invoice_id: uuid.UUID) -> None:
    order = _order_for_invoice(db, invoice_id)
    if order is None or order.payment_status == "paid":
        return
    order.payment_status = "paid"
    order.fulfillment_status = "awaiting_fulfillment"
    order.updated_at = datetime.now(UTC)
    lines = db.scalars(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id))
    for line in lines:
        if line.mode != "lease":
            continue
        db.add(
            HardwareAssignment(
                tenant_id=order.tenant_id,
                order_line_id=line.id,
                item_id=line.item_id,
                store_id=line.store_id,
                store_label=line.store_label,
                quantity=line.quantity,
                monthly_fils=line.monthly_fils,
                deposit_fils=line.deposit_fils,
                status="active",
                deposit_decision="held",
            )
        )


def _line_out(line: HardwareOrderLine) -> HardwareLineOut:
    return HardwareLineOut(
        id=line.id,
        item_id=line.item_id,
        sku=line.sku,
        name=line.name,
        store_id=line.store_id,
        store_label=line.store_label,
        mode=line.mode,
        quantity=line.quantity,
        monthly_fils=line.monthly_fils,
        deposit_fils=line.deposit_fils,
        fee_fils=line.fee_fils,
        purchase_fils=line.purchase_fils,
        delivery_fils=line.delivery_fils,
        device_type=line.device_type or "",
        warranty_months=line.warranty_months or 0,
        installation_fils=line.installation_fils or 0,
        fulfilled_qty=line.fulfilled_qty,
        serials=[str(value) for value in (line.serials or [])],
    )


def _order_out(db: Session, order: HardwareOrder, *, with_lines: bool) -> HardwareOrderOut:
    tenant = db.get(Tenant, order.tenant_id)
    line_query = select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id)
    lines = list(db.scalars(line_query)) if with_lines else []
    count = len(lines) if with_lines else db.scalar(select(func.count()).select_from(line_query.subquery())) or 0
    return HardwareOrderOut(
        id=order.id,
        reference=order.reference,
        tenant_id=order.tenant_id,
        tenant_name=tenant.name if tenant is not None else "",
        invoice_id=order.invoice_id,
        payment_status=order.payment_status,
        fulfillment_status=order.fulfillment_status,
        monthly_fils=order.monthly_fils,
        deposit_fils=order.deposit_fils,
        one_time_fils=order.one_time_fils,
        currency=order.currency,
        line_count=count,
        created_at=order.created_at,
        lines=[_line_out(line) for line in lines],
        assignments=_assignments(db, lines) if with_lines else [],
    )


def orders_for_tenant(db: Session, tenant_id: uuid.UUID) -> list[HardwareOrderOut]:
    rows = list(
        db.scalars(
            select(HardwareOrder)
            .where(HardwareOrder.tenant_id == tenant_id)
            .order_by(HardwareOrder.created_at.desc())
        )
    )
    return [_order_out(db, row, with_lines=True) for row in rows]


def list_orders(
    db: Session, *, query: str | None, payment: str | None, fulfillment: str | None, limit: int, offset: int
) -> tuple[list[HardwareOrderOut], int]:
    statement = select(HardwareOrder)
    if payment:
        statement = statement.where(HardwareOrder.payment_status == payment)
    if fulfillment:
        statement = statement.where(HardwareOrder.fulfillment_status == fulfillment)
    if query:
        like = f"%{query.strip().lower()}%"
        tenant_ids = list(db.scalars(select(Tenant.id).where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))))
        matched = [HardwareOrder.reference.ilike(like)]
        if tenant_ids:
            matched.append(HardwareOrder.tenant_id.in_(tenant_ids))
        statement = statement.where(or_(*matched))
    rows = list(db.scalars(statement.order_by(HardwareOrder.created_at.desc())))
    page = rows[offset : offset + limit]
    return [_order_out(db, row, with_lines=False) for row in page], len(rows)


def _assignments(db: Session, lines: list[HardwareOrderLine]) -> list[HardwareAssignmentOut]:
    if not lines:
        return []
    ids = [line.id for line in lines]
    rows = db.scalars(select(HardwareAssignment).where(HardwareAssignment.order_line_id.in_(ids)))
    return [
        HardwareAssignmentOut(
            id=row.id,
            order_line_id=row.order_line_id,
            store_label=row.store_label,
            serial=row.serial,
            quantity=row.quantity,
            monthly_fils=row.monthly_fils,
            deposit_fils=row.deposit_fils,
            status=row.status,
            deposit_decision=row.deposit_decision,
            delivered_at=row.delivered_at,
            returned_at=row.returned_at,
            condition_note=row.condition_note,
            device_type=row.device_type or "",
            registration_status=row.registration_status or "pending",
            warranty_start=row.warranty_start,
            warranty_end=row.warranty_end,
        )
        for row in rows
    ]


def get_order(db: Session, order_id: uuid.UUID) -> HardwareOrderOut:
    row = db.get(HardwareOrder, order_id)
    if row is None:
        raise ApiError(404, "not_found", "That hardware order does not exist.")
    return _order_out(db, row, with_lines=True)


def _claim_serials(db: Session, serials: list[str], tenant_id: uuid.UUID, keep_line_id: uuid.UUID) -> None:
    for serial in serials:
        taken = db.scalar(
            select(HardwareAssignment).where(
                HardwareAssignment.serial == serial, HardwareAssignment.status != "returned"
            )
        )
        if taken is None or taken.order_line_id == keep_line_id:
            continue
        if taken.tenant_id != tenant_id:
            raise ApiError(409, "serial_taken", "That serial number is registered to another business.")
        raise ApiError(409, "duplicate_serial", "That serial number is already registered.")


def fulfill(db: Session, operator: OperatorPrincipal, order_id: uuid.UUID, data: FulfillmentIn) -> HardwareOrderOut:
    order = db.get(HardwareOrder, order_id)
    if order is None:
        raise ApiError(404, "not_found", "That hardware order does not exist.")
    if order.payment_status != "paid":
        raise ApiError(409, "unpaid", "Fulfill hardware only after the payment is verified. A receipt is not payment.")
    line = db.get(HardwareOrderLine, data.line_id)
    if line is None or line.order_id != order.id:
        raise ApiError(422, "unknown_line", "That line is not on this order.")
    if data.fulfilled_qty > line.quantity:
        raise ApiError(422, "quantity", "Fulfilled quantity cannot exceed the quantity ordered.")
    if len(data.serials) > line.quantity:
        raise ApiError(422, "serials", "Record at most one serial number per unit.")
    previous = line.fulfilled_qty
    item = db.get(HardwareItem, line.item_id)
    delta = data.fulfilled_qty - previous
    if item is not None and item.stock_qty is not None and delta:
        if item.stock_qty < delta:
            raise ApiError(422, "stock", f"Only {item.stock_qty} of {item.name} remain to fulfill.")
        item.stock_qty -= delta
    line.fulfilled_qty = data.fulfilled_qty
    line.serials = [value.strip() for value in data.serials if value.strip()]
    _claim_serials(db, line.serials, order.tenant_id, line.id)
    lines = list(db.scalars(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id)))
    if all(item.fulfilled_qty >= item.quantity for item in lines):
        order.fulfillment_status = "fulfilled"
    elif any(item.fulfilled_qty > 0 for item in lines):
        order.fulfillment_status = "partial"
    else:
        order.fulfillment_status = "awaiting_fulfillment"
    order.notes = data.note.strip() or order.notes
    order.assigned_operator_id = operator.id
    order.updated_at = datetime.now(UTC)
    if data.fulfilled_qty > 0:
        assignment = db.scalar(select(HardwareAssignment).where(HardwareAssignment.order_line_id == line.id))
        if assignment is None and line.mode == "purchase" and (line.device_type or "") in {"WIRED", "ANDROID"}:
            assignment = HardwareAssignment(
                tenant_id=order.tenant_id,
                order_line_id=line.id,
                item_id=line.item_id,
                store_id=line.store_id,
                store_label=line.store_label,
                quantity=line.quantity,
                status="active",
                device_type=line.device_type or "",
            )
            db.add(assignment)
            db.flush()
        if assignment is not None and assignment.delivered_at is None:
            assignment.delivered_at = datetime.now(UTC)
            assignment.serial = line.serials[0] if line.serials else ""
            assignment.device_type = line.device_type or ""
    audit_operator(
        db,
        operator,
        "hardware.fulfill",
        after={"reference": order.reference, "fulfilled_qty": data.fulfilled_qty},
        reason=data.reason,
        tenant_id=order.tenant_id,
    )
    _commit_or_conflict(db, "duplicate_serial", "That serial number is already registered.")
    return _order_out(db, order, with_lines=True)


def decide_deposit(db: Session, operator: OperatorPrincipal, data: DepositDecisionIn) -> None:
    row = db.get(HardwareAssignment, data.assignment_id)
    if row is None:
        raise ApiError(404, "not_found", "That lease assignment does not exist.")
    if data.decision != "held" and not data.condition_note.strip():
        raise ApiError(422, "condition", "Record the return condition before deciding the deposit.")
    if data.decision != "held" and row.returned_at is None and data.decision != "forfeited":
        row.returned_at = datetime.now(UTC)
        row.status = "returned"
    row.deposit_decision = data.decision
    row.condition_note = data.condition_note.strip()
    audit_operator(
        db,
        operator,
        "hardware.deposit",
        after={"decision": data.decision, "assignment_id": str(row.id)},
        reason=data.reason,
        tenant_id=row.tenant_id,
    )
    db.commit()


def _serial_key(value: str) -> str:
    return "".join(value.split()).upper()


def _commit_or_conflict(db: Session, code: str, message: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        log.warning("hardware constraint refused code=%s", code)
        raise ApiError(409, code, message) from None


def _remember(row: HardwareAssignment, event: dict) -> None:
    history = list(row.assignment_history or [])
    history.append(event)
    row.assignment_history = history
    flag_modified(row, "assignment_history")


def _apply_registration(db: Session, row: HardwareAssignment) -> None:
    """Marks a delivered serial registered. Does not approve a card payment or commit."""
    if row.status != "active" or row.delivered_at is None or not (row.serial or "").strip():
        raise ApiError(
            409, "not_delivered", "Register a machine only after it is paid, delivered, and given a serial number."
        )
    if (row.device_type or "") not in {"WIRED", "ANDROID"}:
        raise ApiError(422, "not_ec", "Only a wired or Android EC machine can be registered for card payments.")
    from app.tenancy.models import BillingPlan, Subscription

    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == row.tenant_id))
    plan = None if subscription is None else db.get(BillingPlan, subscription.plan_id)
    modules = list(plan.included_modules or []) if plan is not None else []
    entitled = (
        subscription is not None and subscription.status in {"trialing", "active"} and "card_terminals" in modules
    )
    if not entitled:
        log.warning("ec registration refused assignment=%s code=package_required", row.id)
        raise ApiError(409, "package_required", "Pay by Card is not included on the current package.")
    if row.registration_status == "registered":
        return
    start = row.delivered_at
    months = 0
    line = db.get(HardwareOrderLine, row.order_line_id)
    if line is not None:
        months = line.warranty_months or 0
    row.registration_status = "registered"
    row.warranty_start = start
    if months and start is not None:
        month_index = start.month - 1 + months
        year = start.year + month_index // 12
        month = month_index % 12 + 1
        row.warranty_end = start.replace(year=year, month=month, day=min(start.day, 28))


def register_ec_machine(
    db: Session, operator: OperatorPrincipal, assignment_id: uuid.UUID, reason: str
) -> HardwareAssignmentOut:
    """Records a delivered serial as the tenant's EC machine. It does not open a card session."""
    row = db.get(HardwareAssignment, assignment_id)
    if row is None:
        raise ApiError(404, "not_found", "That hardware assignment does not exist.")
    _apply_registration(db, row)
    audit_operator(
        db,
        operator,
        "hardware.ec.register",
        after={"serial": row.serial, "device_type": row.device_type},
        reason=reason,
        tenant_id=row.tenant_id,
    )
    db.commit()
    return HardwareAssignmentOut(
        id=row.id,
        order_line_id=row.order_line_id,
        store_label=row.store_label,
        serial=row.serial,
        quantity=row.quantity,
        monthly_fils=row.monthly_fils,
        deposit_fils=row.deposit_fils,
        status=row.status,
        deposit_decision=row.deposit_decision,
        delivered_at=row.delivered_at,
        returned_at=row.returned_at,
        condition_note=row.condition_note,
        device_type=row.device_type or "",
        registration_status=row.registration_status,
        warranty_start=row.warranty_start,
        warranty_end=row.warranty_end,
    )


def _owned_assignment(db: Session, tenant_id: uuid.UUID, assignment_id: uuid.UUID) -> HardwareAssignment:
    row = db.get(HardwareAssignment, assignment_id)
    if row is None or row.tenant_id != tenant_id:
        log.warning("ec device refused assignment=%s code=not_found", assignment_id)
        raise ApiError(404, "not_found", "That terminal is not on this business.")
    return row


def ec_devices_for_tenant(db: Session, tenant_id: uuid.UUID) -> list[EcDeviceOut]:
    orders = list(
        db.scalars(
            select(HardwareOrder)
            .where(HardwareOrder.tenant_id == tenant_id, HardwareOrder.payment_status != "canceled")
            .order_by(HardwareOrder.created_at.desc())
        )
    )
    found: list[EcDeviceOut] = []
    for order in orders:
        lines = list(db.scalars(select(HardwareOrderLine).where(HardwareOrderLine.order_id == order.id)))
        for line in lines:
            if (line.device_type or "") not in {"WIRED", "ANDROID"}:
                continue
            assignment = db.scalar(select(HardwareAssignment).where(HardwareAssignment.order_line_id == line.id))
            item = db.get(HardwareItem, line.item_id)
            delivered = assignment is not None and assignment.delivered_at is not None
            registered = assignment is not None and assignment.registration_status == "registered"
            assigned = assignment is not None and assignment.register_id is not None
            specs = item.specifications if item is not None and isinstance(item.specifications, dict) else {}
            found.append(
                EcDeviceOut(
                    assignment_id=None if assignment is None else assignment.id,
                    line_id=line.id,
                    name=line.name,
                    manufacturer="" if item is None else item.manufacturer,
                    model="" if item is None else item.model,
                    device_type=line.device_type or "",
                    serial="" if assignment is None else assignment.serial,
                    label="" if assignment is None else (assignment.label or ""),
                    order_reference=order.reference,
                    payment_status=order.payment_status,
                    fulfillment_status=order.fulfillment_status,
                    delivered_at=None if assignment is None else assignment.delivered_at,
                    registration_status="pending" if assignment is None else assignment.registration_status,
                    store_id=line.store_id if assignment is None else assignment.store_id,
                    store_label=line.store_label if assignment is None else assignment.store_label,
                    register_id=None if assignment is None else assignment.register_id,
                    assigned_at=None if assignment is None else assignment.assigned_at,
                    warranty_months=line.warranty_months or 0,
                    installation_fils=line.installation_fils or 0,
                    purchase_fils=line.purchase_fils or 0,
                    specifications={str(key): str(value) for key, value in specs.items()},
                    history=[] if assignment is None else list(assignment.assignment_history or []),
                    payment_verified=order.payment_status == "paid",
                    delivered=delivered,
                    registered=registered,
                    assigned=assigned,
                )
            )
    return found


def confirm_ec_registration(
    db: Session, tenant_id: uuid.UUID, assignment_id: uuid.UUID, data: EcRegisterIn, actor_id: uuid.UUID
) -> EcDeviceOut:
    """Confirms the serial Console recorded at delivery. A different serial is refused."""
    row = _owned_assignment(db, tenant_id, assignment_id)
    supplied = _serial_key(data.serial)
    recorded = _serial_key(row.serial or "")
    if not recorded or supplied != recorded:
        log.warning("ec registration refused assignment=%s code=serial_mismatch", row.id)
        raise ApiError(409, "serial_mismatch", "Enter the serial number recorded when this machine was delivered.")
    _apply_registration(db, row)
    if data.label.strip():
        row.label = data.label.strip()
    _remember(
        row,
        {
            "action": "register",
            "at": datetime.now(UTC).isoformat(),
            "by": str(actor_id),
            "note": data.note.strip(),
        },
    )
    db.commit()
    devices = ec_devices_for_tenant(db, tenant_id)
    return next(item for item in devices if item.assignment_id == row.id)


def assign_ec_register(
    db: Session,
    tenant_id: uuid.UUID,
    assignment_id: uuid.UUID,
    data: EcAssignIn,
    *,
    stores: dict[uuid.UUID, str],
    registers: dict[uuid.UUID, tuple[uuid.UUID, bool]],
    actor_id: uuid.UUID,
) -> EcDeviceOut:
    """Points a registered machine at one active register in a branch this business owns."""
    row = _owned_assignment(db, tenant_id, assignment_id)
    if row.registration_status != "registered":
        raise ApiError(409, "not_registered", "Register the machine before assigning it to a register.")
    if data.store_id not in stores:
        log.warning("ec assignment refused assignment=%s code=unknown_store", row.id)
        raise ApiError(422, "unknown_store", "Choose a branch this business owns.")
    register = registers.get(data.register_id)
    if register is None or not register[1]:
        raise ApiError(422, "register_inactive", "Choose an active register.")
    if register[0] != data.store_id:
        raise ApiError(422, "register_store", "That register belongs to a different branch.")
    taken = db.scalar(
        select(HardwareAssignment.id).where(
            HardwareAssignment.tenant_id == tenant_id,
            HardwareAssignment.register_id == data.register_id,
            HardwareAssignment.id != row.id,
            HardwareAssignment.status == "active",
        )
    )
    if taken is not None:
        raise ApiError(409, "register_taken", "That register already has an active terminal.")
    previous = None if row.register_id is None else str(row.register_id)
    action = "assign" if previous is None else "reassign"
    row.store_id = data.store_id
    row.store_label = stores[data.store_id]
    row.register_id = data.register_id
    row.assigned_at = datetime.now(UTC)
    row.assigned_by_user_id = actor_id
    _remember(
        row,
        {
            "action": action,
            "at": row.assigned_at.isoformat(),
            "by": str(actor_id),
            "store_id": str(data.store_id),
            "register_id": str(data.register_id),
            "previous_register_id": previous,
        },
    )
    _commit_or_conflict(db, "register_taken", "That register already has an active terminal.")
    devices = ec_devices_for_tenant(db, tenant_id)
    return next(item for item in devices if item.assignment_id == row.id)


def unassign_ec_register(
    db: Session, tenant_id: uuid.UUID, assignment_id: uuid.UUID, actor_id: uuid.UUID
) -> EcDeviceOut:
    row = _owned_assignment(db, tenant_id, assignment_id)
    if row.register_id is None:
        raise ApiError(409, "not_assigned", "This machine is not assigned to a register.")
    previous = str(row.register_id)
    row.register_id = None
    row.assigned_at = None
    _remember(
        row,
        {
            "action": "unassign",
            "at": datetime.now(UTC).isoformat(),
            "by": str(actor_id),
            "previous_register_id": previous,
        },
    )
    db.commit()
    devices = ec_devices_for_tenant(db, tenant_id)
    return next(item for item in devices if item.assignment_id == row.id)


def ec_readiness(db: Session, tenant_id: uuid.UUID, assignment_id: uuid.UUID) -> EcReadinessOut:
    """Reports blockers. A registered machine is not a certified card terminal."""
    row = _owned_assignment(db, tenant_id, assignment_id)
    from app.tenancy.models import BillingPlan, Subscription

    order_line = db.get(HardwareOrderLine, row.order_line_id)
    order = None if order_line is None else db.get(HardwareOrder, order_line.order_id)
    subscription = db.scalar(select(Subscription).where(Subscription.tenant_id == tenant_id))
    plan = None if subscription is None else db.get(BillingPlan, subscription.plan_id)
    modules = list(plan.included_modules or []) if plan is not None else []
    entitled = (
        subscription is not None and subscription.status in {"trialing", "active"} and "card_terminals" in modules
    )
    blockers: list[str] = []
    if not entitled:
        blockers.append("PACKAGE_REQUIRED")
    if order is None or order.payment_status != "paid":
        blockers.append("PAYMENT_PENDING")
    if row.delivered_at is None:
        blockers.append("HARDWARE_NOT_DELIVERED")
    registered = row.registration_status == "registered"
    if not registered:
        blockers.append("DEVICE_NOT_REGISTERED")
    assigned = row.register_id is not None
    if not assigned:
        blockers.append("DEVICE_NOT_ASSIGNED")
    blockers.extend(["DEVICE_CONNECTION_NOT_VERIFIED", "PROVIDER_NOT_CONFIGURED", "INTEGRATION_NOT_CERTIFIED"])
    return EcReadinessOut(
        production_ready=False,
        device_registered=registered,
        device_assigned=assigned,
        device_connected=False,
        provider_configured=False,
        integration_validated=False,
        blockers=blockers,
    )
