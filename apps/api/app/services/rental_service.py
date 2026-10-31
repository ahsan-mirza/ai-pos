"""Fashion rental bookings.

Availability is the units on hand minus rentals whose blocked dates overlap. A blocked date runs from
the start through the return date plus the product's preparation buffer. The refundable deposit is
stored on its own fields and is not added to rental revenue.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.rental import BLOCKING_STATUSES, HELD_STATUSES, ProductRental, Rental, RentalLine, RentalPayment
from app.models.user import User
from app.schemas.rentals import (
    AgreementOut,
    CustomerPick,
    ExtendIn,
    HandoverIn,
    NamedCount,
    RentalCreate,
    RentalLineOut,
    RentalOut,
    RentalPaymentIn,
    RentalPolicyIn,
    RentalPolicyOut,
    RentalQuote,
    RentalSummary,
    ReturnIn,
)
from app.services import audit, inventory, tax
from app.services.settings_service import business_currency, cached_settings

OPEN = ("confirmed", "ready")


def _today() -> date:
    return datetime.now(UTC).date()


def _days(start: date, end: date) -> int:
    if end < start or (end - start).days > 366:
        raise ApiError(422, "validation_error", "Choose a rental that ends after it starts and lasts at most a year.")
    return (end - start).days + 1


def _overlap(left_start: date, left_end: date, right_start: date, right_end: date) -> bool:
    return left_start <= right_end and right_start <= left_end


def _policy(db: Session, product_id: uuid.UUID) -> ProductRental | None:
    return db.scalar(select(ProductRental).where(ProductRental.product_id == product_id))


def rental_only(db: Session, product: Product) -> None:
    """A rental-only catalogue item is refused at the till. Sale-or-rent items are unchanged."""
    row = _policy(db, product.id)
    if row is not None and row.enabled and row.offer == "RENT":
        raise SyncRejected(f"{product.name} is rented, not sold.")


def units_promised_today(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, on: date) -> int:
    """Confirmed bookings that cover today and have not left the shop yet. Out units are already reserved."""
    total = 0
    for start, end, buffer, quantity, _rental_id, _serial in _blocks(db, product_id, store_id, statuses=OPEN):
        if _overlap(start, end + timedelta(days=buffer), on, on):
            total += quantity
    return total


def _blocks(db: Session, product_id: uuid.UUID, store_id: uuid.UUID, statuses: tuple[str, ...] = BLOCKING_STATUSES):
    statement = (
        select(
            Rental.start_date,
            Rental.return_date,
            ProductRental.buffer_days,
            RentalLine.quantity,
            Rental.id,
            RentalLine.serial_number_id,
        )
        .join(RentalLine, RentalLine.rental_id == Rental.id)
        .join(ProductRental, ProductRental.product_id == RentalLine.product_id)
        .where(RentalLine.product_id == product_id, Rental.store_id == store_id, Rental.status.in_(statuses))
    )
    return [
        (start, end, int(buffer or 0), int(quantity), rental_id, serial)
        for start, end, buffer, quantity, rental_id, serial in db.execute(statement)
    ]


def _available(
    db: Session,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    start: date,
    end: date,
    *,
    buffer_days: int,
    quantity: int,
    serial_number_id: uuid.UUID | None,
    exclude: uuid.UUID | None,
) -> int:
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == product_id, InventoryLevel.store_id == store_id)
    )
    on_hand = int(level.quantity_on_hand) if level is not None else 0
    taken = 0
    blocked_end = end + timedelta(days=buffer_days)
    for other_start, other_end, other_buffer, other_qty, rental_id, serial in _blocks(db, product_id, store_id):
        if exclude is not None and rental_id == exclude:
            continue
        other_blocked = other_end + timedelta(days=other_buffer)
        if not _overlap(start, blocked_end, other_start, other_blocked):
            continue
        if serial_number_id is not None and serial == serial_number_id:
            raise ApiError(409, "rental_unavailable", "That individual item is already booked for these dates.")
        taken += other_qty
    remaining = on_hand - taken
    if quantity > remaining:
        raise ApiError(
            409,
            "rental_unavailable",
            f"{max(remaining, 0)} available for those dates. Another date or a smaller quantity is needed.",
        )
    return remaining


def _charge(policy: ProductRental, days: int, quantity: int) -> int:
    if days < policy.min_days or (policy.max_days is not None and days > policy.max_days):
        raise ApiError(422, "validation_error", "That length is outside the rental period configured for this item.")
    if policy.weekly_price_cents is not None and days % 7 == 0:
        return policy.weekly_price_cents * (days // 7) * quantity
    return policy.price_per_day_cents * days * quantity


def _tax(db: Session, product: Product, gross: int, store_id: uuid.UUID) -> tuple[int, int]:
    rules = tax.policy(db, store_id)
    rate = rules.rate_for(product.tax_category) if rules.enforced else 0
    priced = tax.line_tax(gross, 1, rate, inclusive=tax.entered_includes_tax(product))
    return priced.net_cents, priced.tax_cents


def save_policy(db: Session, product_id: uuid.UUID, data: RentalPolicyIn) -> RentalPolicyOut:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product not found.")
    if data.max_days is not None and data.default_days > data.max_days:
        raise ApiError(422, "validation_error", "The default period cannot be longer than the maximum.")
    if data.default_days < data.min_days:
        raise ApiError(422, "validation_error", "The default period cannot be shorter than the minimum.")
    row = _policy(db, product_id)
    if row is None:
        row = ProductRental(product_id=product_id)
        db.add(row)
    for field in RentalPolicyIn.model_fields:
        setattr(row, field, getattr(data, field))
    db.flush()
    return _policy_out(row, product)


def list_policies(db: Session) -> list[RentalPolicyOut]:
    rows = db.execute(select(ProductRental, Product).join(Product, Product.id == ProductRental.product_id)).all()
    return [_policy_out(policy, product) for policy, product in rows]


def _policy_out(row: ProductRental, product: Product) -> RentalPolicyOut:
    return RentalPolicyOut(
        product_id=product.id,
        product_name=product.name,
        sku=product.sku,
        enabled=row.enabled,
        offer=row.offer,  # type: ignore[arg-type]
        price_per_day_cents=row.price_per_day_cents,
        weekly_price_cents=row.weekly_price_cents,
        deposit_cents=row.deposit_cents,
        min_days=row.min_days,
        max_days=row.max_days,
        default_days=row.default_days,
        buffer_days=row.buffer_days,
        late_fee_per_day_cents=row.late_fee_per_day_cents,
        cleaning_fee_cents=row.cleaning_fee_cents,
        requires_inspection=row.requires_inspection,
        condition_note=row.condition_note,
    )


def quote(
    db: Session,
    *,
    product_id: uuid.UUID,
    store_id: uuid.UUID,
    start: date,
    end: date,
    quantity: int,
    discount_cents: int = 0,
) -> RentalQuote:
    product, policy = _rentable(db, product_id)
    days = _days(start, end)
    gross = _charge(policy, days, quantity)
    if discount_cents > gross:
        raise ApiError(422, "validation_error", "The discount cannot be more than the rental charge.")
    net, tax_cents = _tax(db, product, gross - discount_cents, store_id)
    available = _available(
        db,
        product_id,
        store_id,
        start,
        end,
        buffer_days=policy.buffer_days,
        quantity=quantity,
        serial_number_id=None,
        exclude=None,
    )
    deposit = policy.deposit_cents * quantity
    return RentalQuote(
        product_id=product_id,
        days=days,
        quantity=quantity,
        available=available,
        rental_net_cents=net,
        tax_cents=tax_cents,
        deposit_cents=deposit,
        total_due_cents=net + tax_cents,
        currency=business_currency(db),
    )


def _rentable(db: Session, product_id: uuid.UUID) -> tuple[Product, ProductRental]:
    product = db.get(Product, product_id)
    policy = _policy(db, product_id)
    if product is None or policy is None or not policy.enabled or policy.offer == "SALE":
        raise ApiError(422, "not_rentable", "This product is not available to rent.")
    if product.currency != business_currency(db):
        raise ApiError(422, "validation_error", "The product currency has to match the business currency.")
    return product, policy


def create_rental(db: Session, data: RentalCreate, user: User | None) -> RentalOut:
    existing = db.scalar(select(Rental).where(Rental.client_request_id == data.client_request_id))
    if existing is not None:
        return _out(db, existing)
    if data.discount_cents and (user is None or Permission.POS_DISCOUNT.value not in _permissions(user)):
        raise ApiError(403, "forbidden", "A discount on a rental needs the discount permission.")
    product, policy = _rentable(db, data.product_id)
    customer = db.get(Customer, data.customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer not found.")
    days = _days(data.start_date, data.return_date)
    gross = _charge(policy, days, data.quantity)
    if data.discount_cents > gross:
        raise ApiError(422, "validation_error", "The discount cannot be more than the rental charge.")
    _available(
        db,
        data.product_id,
        data.store_id,
        data.start_date,
        data.return_date,
        buffer_days=policy.buffer_days,
        quantity=data.quantity,
        serial_number_id=data.serial_number_id,
        exclude=None,
    )
    net, tax_cents = _tax(db, product, gross - data.discount_cents, data.store_id)
    deposit = policy.deposit_cents * data.quantity
    if data.pay_charge_cents > net + tax_cents or data.pay_deposit_cents > deposit:
        raise ApiError(422, "validation_error", "A payment cannot be more than the charge or the deposit due.")
    rental = Rental(
        reference=_reference(db),
        store_id=data.store_id,
        customer_id=customer.id,
        created_by=user.id if user is not None else None,
        status="confirmed",
        start_date=data.start_date,
        return_date=data.return_date,
        currency=business_currency(db),
        agreed_net_cents=net,
        discount_cents=data.discount_cents,
        tax_cents=tax_cents,
        amount_paid_cents=data.pay_charge_cents,
        deposit_due_cents=deposit,
        deposit_collected_cents=data.pay_deposit_cents,
        client_request_id=data.client_request_id,
        notes=data.notes,
    )
    db.add(rental)
    db.flush()
    db.add(
        RentalLine(
            rental_id=rental.id,
            product_id=product.id,
            quantity=data.quantity,
            serial_number_id=data.serial_number_id,
        )
    )
    db.flush()
    return _out(db, rental)


def _permissions(user: User) -> set[str]:
    if user.role is None:
        return set()
    return set(user.role.permissions)


def _reference(db: Session) -> str:
    latest = db.scalar(select(func.max(Rental.reference)))
    number = int(str(latest).split("-")[1]) + 1 if latest else 1
    return f"RNT-{number:05d}"


def _charges(rental: Rental) -> int:
    return (
        rental.agreed_net_cents
        + rental.tax_cents
        + rental.extension_net_cents
        + rental.extension_tax_cents
        + rental.late_fee_cents
        + rental.cleaning_fee_cents
        + rental.damage_cents
    )


def _held(rental: Rental) -> int:
    return rental.deposit_collected_cents - rental.deposit_refunded_cents - rental.deposit_deducted_cents


def _out(db: Session, rental: Rental) -> RentalOut:
    customer = db.get(Customer, rental.customer_id)
    lines = db.scalars(select(RentalLine).where(RentalLine.rental_id == rental.id)).all()
    product_ids = [line.product_id for line in lines] or [uuid.uuid4()]
    products = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(product_ids)))}
    display = rental.status
    if rental.status == "out" and rental.return_date < _today():
        display = "overdue"
    return RentalOut(
        id=rental.id,
        reference=rental.reference,
        store_id=rental.store_id,
        customer_id=rental.customer_id,
        customer_name=customer.name if customer is not None else "",
        status=rental.status,  # type: ignore[arg-type]
        display_status=display,
        start_date=rental.start_date,
        return_date=rental.return_date,
        currency=rental.currency,
        agreed_net_cents=rental.agreed_net_cents,
        discount_cents=rental.discount_cents,
        tax_cents=rental.tax_cents,
        extension_net_cents=rental.extension_net_cents,
        extension_tax_cents=rental.extension_tax_cents,
        late_fee_cents=rental.late_fee_cents,
        cleaning_fee_cents=rental.cleaning_fee_cents,
        damage_cents=rental.damage_cents,
        amount_paid_cents=rental.amount_paid_cents,
        balance_cents=_charges(rental) - rental.amount_paid_cents,
        deposit_due_cents=rental.deposit_due_cents,
        deposit_collected_cents=rental.deposit_collected_cents,
        deposit_refunded_cents=rental.deposit_refunded_cents,
        deposit_deducted_cents=rental.deposit_deducted_cents,
        deposit_held_cents=_held(rental),
        notes=rental.notes,
        handover_at=rental.handover_at,
        handover_condition=rental.handover_condition,
        returned_at=rental.returned_at,
        return_condition=rental.return_condition,
        return_notes=rental.return_notes,
        lines=[
            RentalLineOut(
                product_id=line.product_id,
                product_name=products[line.product_id].name if line.product_id in products else "",
                sku=products[line.product_id].sku if line.product_id in products else "",
                quantity=line.quantity,
                serial_number_id=line.serial_number_id,
            )
            for line in lines
        ],
    )


def get_rental(db: Session, rental_id: uuid.UUID) -> RentalOut:
    rental = db.get(Rental, rental_id)
    if rental is None:
        raise ApiError(404, "not_found", "Rental not found.")
    return _out(db, rental)


def list_rentals(
    db: Session,
    *,
    store_id: uuid.UUID | None,
    status: str | None,
    product_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    start: date | None,
    end: date | None,
    reference: str | None,
) -> list[RentalOut]:
    statement = select(Rental).order_by(Rental.start_date, Rental.reference)
    if store_id is not None:
        statement = statement.where(Rental.store_id == store_id)
    if customer_id is not None:
        statement = statement.where(Rental.customer_id == customer_id)
    if reference:
        statement = statement.where(Rental.reference.ilike(f"%{reference.strip()}%"))
    if start is not None:
        statement = statement.where(Rental.return_date >= start)
    if end is not None:
        statement = statement.where(Rental.start_date <= end)
    if product_id is not None:
        owned = select(RentalLine.rental_id).where(RentalLine.product_id == product_id)
        statement = statement.where(Rental.id.in_(owned))
    rows = list(db.scalars(statement.limit(200)))
    if status == "overdue":
        rows = [row for row in rows if row.status == "out" and row.return_date < _today()]
    elif status:
        rows = [row for row in rows if row.status == status]
    return [_out(db, row) for row in rows]


def apply_payment(db: Session, rental_id: uuid.UUID, data: RentalPaymentIn, user: User | None) -> RentalOut:
    replay = db.scalar(select(RentalPayment).where(RentalPayment.client_request_id == data.client_request_id))
    if replay is not None:
        return get_rental(db, replay.rental_id)
    rental = _locked(db, rental_id)
    if rental.status in {"cancelled", "completed"}:
        raise ApiError(409, "invalid_status", "This rental is already closed.")
    if data.kind == "charge":
        due = _charges(rental) - rental.amount_paid_cents
        if data.amount_cents > due:
            raise ApiError(422, "validation_error", "That payment is more than the balance.")
        rental.amount_paid_cents += data.amount_cents
    elif data.kind == "deposit":
        room = rental.deposit_due_cents - rental.deposit_collected_cents
        if data.amount_cents > room:
            raise ApiError(422, "validation_error", "That payment is more than the deposit still due.")
        rental.deposit_collected_cents += data.amount_cents
    elif data.kind == "deposit_refund":
        _require_reason(data.reason, "a deposit refund")
        if data.amount_cents > _held(rental):
            raise ApiError(422, "validation_error", "The refund cannot be more than the deposit still held.")
        rental.deposit_refunded_cents += data.amount_cents
    else:
        _require_reason(data.reason, "a deposit deduction")
        if data.amount_cents > _held(rental):
            raise ApiError(422, "validation_error", "The deduction cannot be more than the deposit still held.")
        rental.deposit_deducted_cents += data.amount_cents
        rental.deduction_reason = data.reason
        audit.record(
            db,
            action_type="UPDATE",
            action="rental.deposit_deduction",
            target_entity="Rental",
            target_entity_id=rental.id,
            reason_notes=data.reason,
            user=user,
            details={"amount_cents": data.amount_cents},
        )
    db.add(
        RentalPayment(
            rental_id=rental.id,
            client_request_id=data.client_request_id,
            kind=data.kind,
            amount_cents=data.amount_cents,
            reason=data.reason,
            user_id=user.id if user is not None else None,
        )
    )
    db.flush()
    return _out(db, rental)


def _require_reason(reason: str | None, what: str) -> None:
    if reason is None or len(reason.strip()) < 3:
        raise ApiError(422, "reason_required", f"A reason of at least 3 characters is required for {what}.")


def _locked(db: Session, rental_id: uuid.UUID) -> Rental:
    statement = select(Rental).where(Rental.id == rental_id)
    if db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    rental = db.scalar(statement)
    if rental is None:
        raise ApiError(404, "not_found", "Rental not found.")
    return rental


def _lines(db: Session, rental_id: uuid.UUID) -> list[RentalLine]:
    return list(db.scalars(select(RentalLine).where(RentalLine.rental_id == rental_id)))


def _reserve(db: Session, rental: Rental, sign: int) -> None:
    for line in _lines(db, rental.id):
        level = inventory.level_for(db, line.product_id, rental.store_id)
        next_reserved = level.quantity_reserved + sign * line.quantity
        if next_reserved < 0 or next_reserved > level.quantity_on_hand:
            raise ApiError(409, "stock_conflict", "Stock reserved for this rental no longer matches the shelf.")
        level.quantity_reserved = next_reserved
    db.flush()


def mark_ready(db: Session, rental_id: uuid.UUID) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status != "confirmed":
        raise ApiError(409, "invalid_status", "Only a confirmed booking can be marked ready.")
    rental.status = "ready"
    db.flush()
    return _out(db, rental)


def handover(db: Session, rental_id: uuid.UUID, data: HandoverIn, user: User | None) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status not in OPEN:
        raise ApiError(409, "invalid_status", "Hand the item over from a confirmed or ready booking.")
    _reserve(db, rental, 1)
    rental.status = "out"
    rental.handover_at = datetime.now(UTC)
    rental.handover_condition = data.condition
    rental.handover_by = user.id if user is not None else None
    if data.notes:
        rental.notes = data.notes
    db.flush()
    return _out(db, rental)


def return_rental(db: Session, rental_id: uuid.UUID, data: ReturnIn, user: User | None) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status != "out":
        raise ApiError(409, "invalid_status", "Only an item that is out can be returned.")
    late_days = max((_today() - rental.return_date).days, 0)
    policy = _policy(db, _lines(db, rental.id)[0].product_id)
    proposed = (policy.late_fee_per_day_cents if policy is not None else 0) * late_days
    if proposed and data.waive_late:
        _require_reason(data.waive_reason, "waiving a late fee")
        rental.waived_late_reason = data.waive_reason
        audit.record(
            db,
            action_type="UPDATE",
            action="rental.late_fee_waived",
            target_entity="Rental",
            target_entity_id=rental.id,
            reason_notes=data.waive_reason,
            user=user,
            details={"late_fee_cents": proposed},
        )
    elif proposed:
        rental.late_fee_cents = proposed
    rental.damage_cents = data.damage_cents
    rental.returned_at = datetime.now(UTC)
    rental.return_condition = data.condition
    rental.return_notes = data.notes
    if data.cleaning and policy is not None:
        rental.cleaning_fee_cents = policy.cleaning_fee_cents
        rental.status = "cleaning"
    elif data.repair:
        rental.status = "repair"
    elif policy is not None and policy.requires_inspection:
        rental.status = "inspection"
    else:
        rental.status = "completed"
        _reserve(db, rental, -1)
    db.flush()
    return _out(db, rental)


def release(db: Session, rental_id: uuid.UUID) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status not in {"inspection", "cleaning", "repair"}:
        raise ApiError(409, "invalid_status", "Release an item only after it has been returned.")
    if rental.status in HELD_STATUSES:
        _reserve(db, rental, -1)
    rental.status = "completed"
    db.flush()
    return _out(db, rental)


def extend(db: Session, rental_id: uuid.UUID, data: ExtendIn) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status not in {"confirmed", "ready", "out"}:
        raise ApiError(409, "invalid_status", "Only an open rental can be extended.")
    if data.return_date <= rental.return_date:
        raise ApiError(422, "validation_error", "The new return date has to be after the current one.")
    line = _lines(db, rental.id)[0]
    product, policy = _rentable(db, line.product_id)
    extra_days = (data.return_date - rental.return_date).days
    _available(
        db,
        line.product_id,
        rental.store_id,
        rental.return_date + timedelta(days=1),
        data.return_date,
        buffer_days=policy.buffer_days,
        quantity=line.quantity,
        serial_number_id=line.serial_number_id,
        exclude=rental.id,
    )
    extra_gross = policy.price_per_day_cents * extra_days * line.quantity
    net, tax_cents = _tax(db, product, extra_gross, rental.store_id)
    rental.return_date = data.return_date
    rental.extension_net_cents += net
    rental.extension_tax_cents += tax_cents
    db.flush()
    return _out(db, rental)


def cancel(db: Session, rental_id: uuid.UUID) -> RentalOut:
    rental = _locked(db, rental_id)
    if rental.status not in OPEN:
        raise ApiError(409, "invalid_status", "Cancel a booking before the item is handed over.")
    rental.status = "cancelled"
    db.flush()
    return _out(db, rental)


def agreement(db: Session, rental_id: uuid.UUID) -> AgreementOut:
    body = get_rental(db, rental_id)
    settings = cached_settings(db)
    text = "\n".join(
        [
            f"{settings.legal_name or 'This business'} rental record {body.reference}",
            f"Customer: {body.customer_name}",
            f"Item: {body.lines[0].product_name} × {body.lines[0].quantity}" if body.lines else "Item: —",
            f"From {body.start_date.isoformat()} to {body.return_date.isoformat()}",
            f"Rental charge {body.agreed_net_cents} {body.currency} fils, tax {body.tax_cents} fils.",
            f"Refundable deposit due {body.deposit_due_cents} fils. Collected {body.deposit_collected_cents} fils.",
            "The deposit is held apart from rental revenue and is refunded after inspection, less approved deductions.",
            "A late return can add the configured daily late fee. An extension is priced only for the extra days.",
            "This record states the agreed charges. It is not a jurisdiction-specific legal contract.",
        ]
    )
    return AgreementOut(reference=body.reference, text=text)


def summary(db: Session, store_id: uuid.UUID | None, start: date, end: date) -> RentalSummary:
    statement = select(Rental).where(Rental.start_date <= end, Rental.return_date >= start)
    if store_id is not None:
        statement = statement.where(Rental.store_id == store_id)
    rows = list(db.scalars(statement))
    today = _today()
    active = [row for row in rows if row.status not in {"cancelled"}]
    revenue = sum(row.agreed_net_cents + row.extension_net_cents for row in active)
    fees = sum(row.late_fee_cents + row.cleaning_fee_cents + row.damage_cents for row in active)
    held = sum(_held(row) for row in active)
    outstanding = sum(_charges(row) - row.amount_paid_cents for row in active)
    names = dict(db.execute(select(Product.id, Product.name)).all())
    counts: dict[uuid.UUID, int] = {}
    if active:
        for product_id, quantity in db.execute(
            select(RentalLine.product_id, func.sum(RentalLine.quantity))
            .where(RentalLine.rental_id.in_([row.id for row in active]))
            .group_by(RentalLine.product_id)
        ):
            counts[product_id] = int(quantity)
    ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)[:5]
    return RentalSummary(
        currency=business_currency(db),
        pickups_today=sum(1 for row in rows if row.status in OPEN and row.start_date == today),
        returns_today=sum(1 for row in rows if row.status == "out" and row.return_date == today),
        active=sum(1 for row in rows if row.status == "out"),
        overdue=sum(1 for row in rows if row.status == "out" and row.return_date < today),
        in_preparation=sum(1 for row in rows if row.status in {"inspection", "cleaning", "repair"}),
        rental_revenue_cents=revenue,
        fee_cents=fees,
        deposits_held_cents=held,
        outstanding_cents=outstanding,
        most_rented=[NamedCount(name=str(names.get(product_id, "Item")), count=count) for product_id, count in ranked],
    )


def search_customers(db: Session, query: str) -> list[CustomerPick]:
    needle = f"%{query.strip()}%"
    rows = db.scalars(
        select(Customer).where(Customer.name.ilike(needle) | Customer.phone.ilike(needle)).limit(8)
    ).all()
    return [CustomerPick(id=row.id, name=row.name, phone=row.phone) for row in rows]
