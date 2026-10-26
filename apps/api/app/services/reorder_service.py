"""Recurring customer reorder reminders.

A due plan opens one occurrence and, when the plan asks, queues a customer message. It never confirms a sales
order or moves stock. Confirming still goes through the sales-order workflow. Dates are interpreted in the
plan's timezone. A missed run opens the latest due date only, so a restart does not flood the till with old days.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.cache import claim, delete, get_value, set_value
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.pagination import count_rows
from app.models.customer import Customer
from app.models.inventory import InventoryLevel
from app.models.messaging import OutboundMessage
from app.models.product import Product
from app.models.reorder import CustomerReorderOccurrence, CustomerReorderPlan, CustomerReorderPlanItem
from app.models.sales_order import SalesOrder
from app.models.store import Store
from app.models.user import User
from app.schemas.reorders import (
    DraftOrderIn,
    LinkOrderIn,
    OccurrenceOut,
    PlanIn,
    PlanItemIn,
    PlanItemOut,
    PlanOut,
    PlanUpdate,
    SkipIn,
    SnoozeIn,
    SummaryOut,
)
from app.schemas.sales_orders import SalesOrderCreate, SalesOrderLineIn, SalesOrderOut
from app.services import audit, messaging_service, sales_order_service, uom_service
from app.tenancy.context import current_tenant

logger = logging.getLogger("ai_pos.reorders")
OPEN = ("PENDING", "SNOOZED")
NOTIFY_KEY = "reorder:{}"


def has_open_plans(db: Session) -> bool:
    return (
        db.scalar(select(CustomerReorderPlan.id).where(CustomerReorderPlan.status != "ARCHIVED").limit(1)) is not None
    )


def local_today(timezone: str) -> date:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("Asia/Dubai")
    return datetime.now(zone).date()


def following(plan: CustomerReorderPlan, current: date) -> date | None:
    if plan.frequency == "DAILY":
        return current + timedelta(days=1)
    if plan.frequency == "WEEKLY":
        return current + timedelta(days=7)
    if plan.frequency == "MONTHLY":
        day = plan.month_day or current.day
        month = current.month + 1
        year = current.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return date(year, month, min(day, 28))
    days = sorted({int(day) for day in (plan.weekdays or []) if 0 <= int(day) <= 6})
    for offset in range(1, 8):
        candidate = current + timedelta(days=offset)
        if candidate.weekday() in days:
            return candidate
    return None


def _summary_key() -> str:
    tenant = current_tenant()
    return f"tenant:{tenant.id if tenant else 'local'}:reorders:summary"


def _forget_summary() -> None:
    delete(_summary_key())


def _check_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ApiError(422, "invalid_request", f"{name} is not a known timezone.") from exc
    return name


def _check_schedule(data: PlanIn | PlanUpdate, *, frequency: str, weekdays: list[int], month_day: int | None) -> None:
    if frequency == "CUSTOM_DAYS" and not weekdays:
        raise ApiError(422, "invalid_request", "Choose at least one day of the week.")
    if any(day < 0 or day > 6 for day in weekdays):
        raise ApiError(422, "invalid_request", "Weekdays are Monday (0) through Sunday (6).")
    if frequency == "MONTHLY" and month_day is None:
        raise ApiError(422, "invalid_request", "Choose the day of the month, from 1 to 28.")
    start = getattr(data, "start_on", None)
    end = getattr(data, "end_on", None)
    if start is not None and end is not None and end < start:
        raise ApiError(422, "invalid_request", "The end date is before the start date.")


def _items(db: Session, rows: list[PlanItemIn]) -> list[tuple[PlanItemIn, Product, int]]:
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_({row.product_id for row in rows}))).all()
    }
    prepared: list[tuple[PlanItemIn, Product, int]] = []
    for row in rows:
        product = products.get(row.product_id)
        if product is None:
            raise ApiError(422, "invalid_request", "One of the products is not in this store's catalog.")
        if product.is_ingredient:
            raise ApiError(422, "invalid_request", f"{product.name} is an ingredient and is not sold on its own.")
        unit = row.unit.strip().upper()
        allowed = list(product.sellable_units or ["PIECE"])
        if unit not in allowed and unit != "PIECE":
            raise ApiError(422, "invalid_request", f"{product.name} is not sold by the {unit}.")
        if product.sold_by_weight and unit != "PIECE":
            raise ApiError(422, "invalid_request", f"{product.name} is sold by weight. Enter the quantity in grams.")
        factor = uom_service.factor_of(db, unit)
        if factor is None:
            raise ApiError(422, "unknown_unit", f"There is no unit {unit}.")
        if row.quantity * factor > 100_000:
            raise ApiError(422, "invalid_request", f"The quantity of {product.name} is too large for one order.")
        prepared.append((row, product, factor))
    return prepared


def _replace_items(db: Session, plan: CustomerReorderPlan, rows: list[PlanItemIn]) -> None:
    prepared = _items(db, rows)
    plan.items.clear()
    db.flush()
    for position, (row, product, _factor) in enumerate(prepared):
        plan.items.append(
            CustomerReorderPlanItem(
                id=uuid.uuid4(),
                plan_id=plan.id,
                product_id=product.id,
                quantity=row.quantity,
                unit=row.unit.strip().upper(),
                note=(row.note or "").strip() or None,
                position=position,
            )
        )


def _actor_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


def _load_customer(db: Session, customer_id: uuid.UUID) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    if not customer.is_active:
        raise ApiError(409, "customer_inactive", f"{customer.name} is inactive. Reactivate the account first.")
    return customer


def _check_refs(
    db: Session, principal: Principal, salesperson_id: uuid.UUID | None, store_id: uuid.UUID | None
) -> None:
    if salesperson_id is not None and db.get(User, salesperson_id) is None:
        raise ApiError(422, "invalid_request", "The salesperson was not found.")
    if store_id is not None and db.get(Store, store_id) is None:
        raise ApiError(422, "invalid_request", "The branch was not found.")
    if principal.store_id is not None and store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "forbidden", "That branch is outside your store.")


def create_plan(db: Session, principal: Principal, data: PlanIn) -> PlanOut:
    _check_schedule(data, frequency=data.frequency, weekdays=data.weekdays, month_day=data.month_day)
    _check_zone(data.timezone)
    customer = _load_customer(db, data.customer_id)
    _check_refs(db, principal, data.salesperson_id, data.store_id)
    plan = CustomerReorderPlan(
        id=uuid.uuid4(),
        customer_id=customer.id,
        name=data.name.strip(),
        frequency=data.frequency,
        weekdays=sorted(set(data.weekdays)) or None,
        month_day=data.month_day,
        start_on=data.start_on,
        end_on=data.end_on,
        next_on=data.start_on,
        preferred_time=data.preferred_time,
        timezone=data.timezone,
        lead_days=data.lead_days,
        fulfillment=data.fulfillment,
        delivery_address=(data.delivery_address or "").strip() or customer.address,
        notes=data.notes.strip(),
        status="ACTIVE",
        salesperson_id=data.salesperson_id,
        store_id=data.store_id or principal.store_id,
        notify_customer=data.notify_customer,
        created_by_id=_actor_id(principal),
        updated_by_id=_actor_id(principal),
    )
    db.add(plan)
    db.flush()
    _replace_items(db, plan, data.items)
    audit.record(
        db,
        action_type="CREATE",
        action="reorder_plan.create",
        target_entity="CustomerReorderPlan",
        target_entity_id=plan.id,
        user=principal.user,
        new_values={"customer_id": str(customer.id), "frequency": plan.frequency, "items": len(plan.items)},
    )
    db.commit()
    _forget_summary()
    logger.info("reorder plan %s created", plan.id)
    return plan_out(db, _plan(db, plan.id))


def update_plan(db: Session, principal: Principal, plan_id: uuid.UUID, data: PlanUpdate) -> PlanOut:
    plan = _plan(db, plan_id, lock=True)
    if plan.status in {"COMPLETED", "ARCHIVED"}:
        raise ApiError(409, "plan_closed", "This plan is closed. Start a new one for future deliveries.")
    frequency = data.frequency or plan.frequency
    weekdays = plan.weekdays or [] if data.weekdays is None else data.weekdays
    month_day = plan.month_day if data.month_day is None else data.month_day
    _check_schedule(data, frequency=frequency, weekdays=list(weekdays), month_day=month_day)
    if data.timezone is not None:
        _check_zone(data.timezone)
        plan.timezone = data.timezone
    _check_refs(db, principal, data.salesperson_id, data.store_id)
    if data.name is not None:
        plan.name = data.name.strip()
    plan.frequency = frequency
    plan.weekdays = sorted(set(weekdays)) or None
    plan.month_day = month_day
    if data.start_on is not None:
        plan.start_on = data.start_on
    if data.clear_end:
        plan.end_on = None
    elif data.end_on is not None:
        plan.end_on = data.end_on
    if plan.end_on is not None and plan.end_on < plan.start_on:
        raise ApiError(422, "invalid_request", "The end date is before the start date.")
    if data.preferred_time is not None:
        plan.preferred_time = data.preferred_time
    if data.lead_days is not None:
        plan.lead_days = data.lead_days
    if data.fulfillment is not None:
        plan.fulfillment = data.fulfillment
    if data.delivery_address is not None:
        plan.delivery_address = data.delivery_address.strip() or None
    if data.notes is not None:
        plan.notes = data.notes.strip()
    if data.clear_salesperson:
        plan.salesperson_id = None
    elif data.salesperson_id is not None:
        plan.salesperson_id = data.salesperson_id
    if data.store_id is not None:
        plan.store_id = data.store_id
    if data.notify_customer is not None:
        plan.notify_customer = data.notify_customer
    if data.items is not None:
        _replace_items(db, plan, data.items)
    if data.frequency is not None or data.start_on is not None or data.weekdays is not None:
        _advance_without_backfill(plan, local_today(plan.timezone))
    plan.updated_by_id = _actor_id(principal)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_plan.update",
        target_entity="CustomerReorderPlan",
        target_entity_id=plan.id,
        user=principal.user,
        new_values={"frequency": plan.frequency, "next_on": str(plan.next_on) if plan.next_on else None},
    )
    db.commit()
    _forget_summary()
    return plan_out(db, _plan(db, plan.id))


def _advance_without_backfill(plan: CustomerReorderPlan, today: date) -> None:
    """Moves the next date onto today or later. Past dates are not turned into reminders."""
    cursor = plan.start_on if plan.next_on is None or plan.next_on < plan.start_on else plan.next_on
    if cursor < today:
        cursor = today
    guard = 0
    while cursor < today and guard < 400:
        nxt = following(plan, cursor)
        if nxt is None:
            plan.status = "COMPLETED"
            plan.next_on = None
            return
        cursor = nxt
        guard += 1
    if plan.frequency == "CUSTOM_DAYS" and cursor.weekday() not in set(plan.weekdays or []):
        nxt = following(plan, cursor)
        cursor = nxt or cursor
    if plan.end_on is not None and cursor > plan.end_on:
        plan.status = "COMPLETED"
        plan.next_on = None
        return
    plan.next_on = cursor


def pause_plan(db: Session, principal: Principal, plan_id: uuid.UUID) -> PlanOut:
    plan = _plan(db, plan_id, lock=True)
    if plan.status != "ACTIVE":
        raise ApiError(409, "plan_closed", "Only an active plan can be paused.")
    plan.status = "PAUSED"
    plan.updated_by_id = _actor_id(principal)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_plan.pause",
        target_entity="CustomerReorderPlan",
        target_entity_id=plan.id,
        user=principal.user,
    )
    db.commit()
    _forget_summary()
    return plan_out(db, plan)


def resume_plan(db: Session, principal: Principal, plan_id: uuid.UUID) -> PlanOut:
    plan = _plan(db, plan_id, lock=True)
    if plan.status != "PAUSED":
        raise ApiError(409, "plan_closed", "Only a paused plan can be resumed.")
    plan.status = "ACTIVE"
    _advance_without_backfill(plan, local_today(plan.timezone))
    plan.updated_by_id = _actor_id(principal)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_plan.resume",
        target_entity="CustomerReorderPlan",
        target_entity_id=plan.id,
        user=principal.user,
        new_values={"next_on": str(plan.next_on) if plan.next_on else None},
    )
    db.commit()
    _forget_summary()
    return plan_out(db, plan)


def archive_plan(db: Session, principal: Principal, plan_id: uuid.UUID) -> PlanOut:
    plan = _plan(db, plan_id, lock=True)
    plan.status = "ARCHIVED"
    plan.updated_by_id = _actor_id(principal)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_plan.archive",
        target_entity="CustomerReorderPlan",
        target_entity_id=plan.id,
        user=principal.user,
    )
    db.commit()
    _forget_summary()
    return plan_out(db, plan)


def _plan(db: Session, plan_id: uuid.UUID, *, lock: bool = False) -> CustomerReorderPlan:
    stmt = (
        select(CustomerReorderPlan)
        .where(CustomerReorderPlan.id == plan_id)
        .options(selectinload(CustomerReorderPlan.items), selectinload(CustomerReorderPlan.customer))
    )
    if lock:
        stmt = stmt.with_for_update()
    plan = db.scalar(stmt)
    if plan is None:
        raise ApiError(404, "not_found", "Reorder plan was not found.")
    return plan


def get_plan(db: Session, plan_id: uuid.UUID) -> PlanOut:
    return plan_out(db, _plan(db, plan_id))


def list_plans(
    db: Session,
    *,
    offset: int,
    limit: int,
    q: str | None,
    status: str | None,
    customer_id: uuid.UUID | None,
    salesperson_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
) -> tuple[list[PlanOut], int]:
    stmt = select(CustomerReorderPlan).options(
        selectinload(CustomerReorderPlan.items), selectinload(CustomerReorderPlan.customer)
    )
    stmt = _plan_filters(
        stmt, q=q, status=status, customer_id=customer_id, salesperson_id=salesperson_id, store_id=store_id
    )
    total = count_rows(db, stmt)
    rows = db.scalars(
        stmt.order_by(CustomerReorderPlan.next_on, CustomerReorderPlan.name).offset(offset).limit(limit)
    ).all()
    return [plan_out(db, row) for row in rows], total


def _plan_filters(stmt, *, q, status, customer_id, salesperson_id, store_id):
    if status:
        stmt = stmt.where(CustomerReorderPlan.status == status)
    if customer_id is not None:
        stmt = stmt.where(CustomerReorderPlan.customer_id == customer_id)
    if salesperson_id is not None:
        stmt = stmt.where(CustomerReorderPlan.salesperson_id == salesperson_id)
    if store_id is not None:
        stmt = stmt.where(CustomerReorderPlan.store_id == store_id)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.join(Customer, Customer.id == CustomerReorderPlan.customer_id).where(
            or_(CustomerReorderPlan.name.ilike(like), Customer.name.ilike(like), Customer.code.ilike(like))
        )
    return stmt


def list_occurrences(
    db: Session,
    *,
    offset: int,
    limit: int,
    q: str | None,
    status: str | None,
    customer_id: uuid.UUID | None,
    salesperson_id: uuid.UUID | None,
    store_id: uuid.UUID | None,
    date_from: date | None,
    date_to: date | None,
    view: str | None,
    today: date | None = None,
) -> tuple[list[OccurrenceOut], int]:
    day = today or date.today()
    stmt = select(CustomerReorderOccurrence).options(
        selectinload(CustomerReorderOccurrence.plan).selectinload(CustomerReorderPlan.items),
        selectinload(CustomerReorderOccurrence.plan).selectinload(CustomerReorderPlan.customer),
        selectinload(CustomerReorderOccurrence.sales_order),
    )
    stmt = stmt.join(CustomerReorderPlan, CustomerReorderPlan.id == CustomerReorderOccurrence.plan_id)
    if status:
        stmt = stmt.where(CustomerReorderOccurrence.status == status)
    if customer_id is not None:
        stmt = stmt.where(CustomerReorderPlan.customer_id == customer_id)
    if salesperson_id is not None:
        stmt = stmt.where(CustomerReorderPlan.salesperson_id == salesperson_id)
    if store_id is not None:
        stmt = stmt.where(CustomerReorderPlan.store_id == store_id)
    if date_from is not None:
        stmt = stmt.where(CustomerReorderOccurrence.scheduled_on >= date_from)
    if date_to is not None:
        stmt = stmt.where(CustomerReorderOccurrence.scheduled_on <= date_to)
    if view == "due":
        stmt = stmt.where(
            CustomerReorderOccurrence.status.in_(OPEN), CustomerReorderOccurrence.scheduled_on <= day
        )
    elif view == "overdue":
        stmt = stmt.where(CustomerReorderOccurrence.status.in_(OPEN), CustomerReorderOccurrence.scheduled_on < day)
    elif view == "upcoming":
        stmt = stmt.where(CustomerReorderOccurrence.status.in_(OPEN), CustomerReorderOccurrence.scheduled_on > day)
    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = (
            stmt.join(Customer, Customer.id == CustomerReorderPlan.customer_id)
            .outerjoin(SalesOrder, SalesOrder.id == CustomerReorderOccurrence.sales_order_id)
            .outerjoin(User, User.id == CustomerReorderPlan.salesperson_id)
            .where(
                or_(
                    Customer.name.ilike(like),
                    Customer.code.ilike(like),
                    CustomerReorderPlan.name.ilike(like),
                    SalesOrder.number.ilike(like),
                    User.full_name.ilike(like),
                    select(CustomerReorderPlanItem.id)
                    .join(Product, Product.id == CustomerReorderPlanItem.product_id)
                    .where(
                        CustomerReorderPlanItem.plan_id == CustomerReorderPlan.id,
                        Product.name.ilike(like),
                    )
                    .exists(),
                )
            )
        )
    total = count_rows(db, stmt)
    rows = db.scalars(
        stmt.order_by(CustomerReorderOccurrence.scheduled_on.desc(), CustomerReorderOccurrence.created_at.desc())
        .offset(offset)
        .limit(limit)
    ).unique().all()
    notes = _messages(db, rows)
    stock = _availability(db, [item.product_id for row in rows for item in row.plan.items], None)
    return [occurrence_out(db, row, notes, stock) for row in rows], total


def summary(db: Session, *, today: date | None = None) -> SummaryOut:
    cached = get_value(_summary_key())
    if cached and today is None:
        return SummaryOut.model_validate_json(cached)
    day = today or date.today()
    due = _count(db, CustomerReorderOccurrence.status.in_(OPEN), CustomerReorderOccurrence.scheduled_on == day)
    overdue = _count(db, CustomerReorderOccurrence.status.in_(OPEN), CustomerReorderOccurrence.scheduled_on < day)
    pending = _count(db, CustomerReorderOccurrence.status.in_(OPEN))
    ordered = _count(db, CustomerReorderOccurrence.status == "ORDERED")
    active = int(
        db.scalar(select(func.count()).select_from(CustomerReorderPlan).where(CustomerReorderPlan.status == "ACTIVE"))
        or 0
    )
    paused = int(
        db.scalar(select(func.count()).select_from(CustomerReorderPlan).where(CustomerReorderPlan.status == "PAUSED"))
        or 0
    )
    found = SummaryOut(
        due_today=due, overdue=overdue, pending=pending, ordered=ordered, active_plans=active, paused_plans=paused
    )
    if today is None:
        set_value(_summary_key(), found.model_dump_json(), 30)
    return found


def _count(db: Session, *where) -> int:
    return int(db.scalar(select(func.count()).select_from(CustomerReorderOccurrence).where(*where)) or 0)


def generate_due(db: Session, *, today_for: Callable[[str], date] | None = None) -> str:
    clock = today_for or local_today
    plans = db.scalars(
        select(CustomerReorderPlan)
        .where(CustomerReorderPlan.status == "ACTIVE", CustomerReorderPlan.next_on.is_not(None))
        .options(selectinload(CustomerReorderPlan.items), selectinload(CustomerReorderPlan.customer))
    ).all()
    opened = 0
    for plan in plans:
        today = clock(plan.timezone)
        horizon = today + timedelta(days=plan.lead_days)
        if plan.next_on is None or plan.next_on > horizon:
            continue
        if plan.end_on is not None and plan.next_on > plan.end_on:
            plan.status = "COMPLETED"
            plan.next_on = None
            continue
        scheduled = plan.next_on
        guard = 0
        while guard < 400:
            nxt = following(plan, scheduled)
            if nxt is None or nxt > horizon or (plan.end_on is not None and nxt > plan.end_on):
                break
            scheduled = nxt
            guard += 1
        if _open_occurrence(db, plan, scheduled):
            opened += 1
        nxt = following(plan, scheduled)
        if nxt is None or (plan.end_on is not None and nxt > plan.end_on):
            plan.status = "COMPLETED"
            plan.next_on = None
        else:
            plan.next_on = nxt
    db.commit()
    _forget_summary()
    return f"{opened} reorder reminders"


def _open_occurrence(db: Session, plan: CustomerReorderPlan, scheduled: date) -> bool:
    existing = db.scalar(
        select(CustomerReorderOccurrence.id).where(
            CustomerReorderOccurrence.plan_id == plan.id,
            CustomerReorderOccurrence.scheduled_on == scheduled,
        )
    )
    if existing is not None:
        return False
    note = _stock_note(db, plan)
    row = CustomerReorderOccurrence(
        id=uuid.uuid4(),
        plan_id=plan.id,
        scheduled_on=scheduled,
        status="PENDING",
        stock_note=note[:500],
        notification_status="PENDING",
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        logger.info("reorder plan %s already has %s", plan.id, scheduled)
        return False
    _notify(db, plan, row)
    audit.record(
        db,
        action_type="CREATE",
        action="reorder_occurrence.open",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        new_values={"plan_id": str(plan.id), "scheduled_on": scheduled.isoformat()},
    )
    logger.info("reorder occurrence %s opened for plan %s", row.id, plan.id)
    return True


def _stock_note(db: Session, plan: CustomerReorderPlan) -> str:
    notes: list[str] = []
    if plan.customer is not None and not plan.customer.is_active:
        notes.append(f"{plan.customer.name} is inactive.")
    products = {
        product.id: product
        for product in db.scalars(
            select(Product).where(Product.id.in_({item.product_id for item in plan.items}))
        ).all()
    }
    available = _availability(db, list(products), plan.store_id)
    for item in plan.items:
        product = products.get(item.product_id)
        if product is None or product.is_ingredient:
            notes.append("A product on this plan is no longer in the catalog.")
            continue
        factor = uom_service.factor_of(db, item.unit) or 1
        needed = item.quantity * factor
        on_hand = available.get(product.id)
        if product.is_stock_tracked and on_hand is not None and on_hand < needed:
            notes.append(f"{product.name}: {on_hand} available, {needed} expected.")
    return " ".join(notes)


def _availability(db: Session, product_ids: list[uuid.UUID], store_id: uuid.UUID | None) -> dict[uuid.UUID, int]:
    if not product_ids:
        return {}
    stmt = (
        select(
            InventoryLevel.product_id,
            func.sum(InventoryLevel.quantity_on_hand - InventoryLevel.quantity_reserved),
        )
        .where(InventoryLevel.product_id.in_(set(product_ids)))
        .group_by(InventoryLevel.product_id)
    )
    if store_id is not None:
        stmt = stmt.where(InventoryLevel.store_id == store_id)
    return {product_id: int(qty or 0) for product_id, qty in db.execute(stmt)}


def _notify(db: Session, plan: CustomerReorderPlan, row: CustomerReorderOccurrence) -> None:
    if not plan.notify_customer:
        row.notification_status = "SKIPPED"
        row.notification_error = "Customer reminders are off for this plan."
        return
    customer = plan.customer or db.get(Customer, plan.customer_id)
    if customer is None or not customer.is_active:
        row.notification_status = "SKIPPED"
        row.notification_error = "Customer is inactive."
        return
    key = NOTIFY_KEY.format(row.id)
    if not claim(f"reorder-notify:{row.id}", 86_400):
        found = db.scalar(select(OutboundMessage).where(OutboundMessage.dedupe_key == key))
        if found is not None:
            row.notification_status = found.status
            row.notification_error = (found.last_error or "")[:255] or None
        return
    message = messaging_service.enqueue(
        db,
        template_key="reorder_due",
        customer=customer,
        context={"plan": plan.name, "date": row.scheduled_on.isoformat(), "store": ""},
        dedupe_key=key,
    )
    if message is None:
        found = db.scalar(select(OutboundMessage).where(OutboundMessage.dedupe_key == key))
        row.notification_status = found.status if found is not None else "SKIPPED"
        row.notification_error = None if found is not None else "Customer reminders are switched off."
        return
    row.notification_status = message.status
    row.notification_error = (message.last_error or "")[:255] or None


def retry_notification(db: Session, occurrence_id: uuid.UUID) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id, lock=True)
    key = NOTIFY_KEY.format(row.id)
    message = db.scalar(select(OutboundMessage).where(OutboundMessage.dedupe_key == key))
    if message is None:
        delete(f"reorder-notify:{row.id}")
        _notify(db, row.plan, row)
    elif message.status == "FAILED":
        message.status = "QUEUED"
        message.attempts = 0
        message.next_attempt_at = datetime.now(UTC)
        message.last_error = None
        row.notification_status = "QUEUED"
        row.notification_error = None
    elif message.status == "SKIPPED":
        row.notification_status = "SKIPPED"
        row.notification_error = (message.last_error or "The customer has not opted in.")[:255]
    else:
        row.notification_status = message.status
    db.commit()
    return _one(db, row.id)


def snooze(db: Session, principal: Principal, occurrence_id: uuid.UUID, data: SnoozeIn) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id, lock=True)
    if row.status not in OPEN:
        raise ApiError(409, "occurrence_closed", "This reminder is already finished.")
    if data.until is None and data.hours is None:
        raise ApiError(422, "invalid_request", "Choose how long to snooze the reminder.")
    until = data.until or (datetime.now(UTC) + timedelta(hours=data.hours or 1))
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    row.status = "SNOOZED"
    row.snooze_until = until
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_occurrence.snooze",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        user=principal.user,
        new_values={"snooze_until": until.isoformat()},
    )
    db.commit()
    _forget_summary()
    return _one(db, row.id)


def skip(db: Session, principal: Principal, occurrence_id: uuid.UUID, data: SkipIn) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id, lock=True)
    if row.status not in OPEN:
        raise ApiError(409, "occurrence_closed", "This reminder is already finished.")
    row.status = "SKIPPED"
    row.skip_reason = data.reason.strip()
    row.completed_at = datetime.now(UTC)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_occurrence.skip",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        user=principal.user,
        reason_notes=row.skip_reason,
    )
    db.commit()
    _forget_summary()
    return _one(db, row.id)


def create_draft(db: Session, principal: Principal, occurrence_id: uuid.UUID, data: DraftOrderIn) -> SalesOrderOut:
    row = _occurrence(db, occurrence_id, lock=True)
    if row.sales_order_id is not None:
        return sales_order_service.get_order(db, principal, row.sales_order_id)
    if row.status == "SKIPPED":
        raise ApiError(409, "occurrence_closed", "This reminder was skipped.")
    plan = row.plan
    customer = plan.customer
    if customer is None or not customer.is_active:
        raise ApiError(409, "customer_inactive", "The customer is inactive, so the order was not created.")
    store_id = plan.store_id or principal.store_id
    if store_id is None:
        store_id = db.scalar(select(Store.id).order_by(Store.code).limit(1))
    if store_id is None:
        raise ApiError(422, "invalid_request", "Choose a branch for this order.")
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "forbidden", "That branch is outside your store.")
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in plan.items}))).all()
    }
    missing = [
        item
        for item in plan.items
        if item.product_id not in products or products[item.product_id].is_ingredient
    ]
    if missing:
        names = ", ".join(
            products[item.product_id].name if item.product_id in products else "A product" for item in missing
        )
        raise ApiError(409, "product_unavailable", f"{names} is no longer sold from this catalog.")
    lines: list[SalesOrderLineIn] = []
    for item in plan.items:
        product = products[item.product_id]
        factor = uom_service.factor_of(db, item.unit) or 1
        label = uom_service.label(db, item.unit)
        description = product.name if item.unit == "PIECE" else f"{product.name} ({item.quantity} {label})"
        lines.append(
            SalesOrderLineIn(product_id=product.id, quantity=item.quantity * factor, description=description[:160])
        )
    payload = SalesOrderCreate(
        id=row.id,
        store_id=store_id,
        customer_id=customer.id,
        sale_type="WHOLESALE" if customer.customer_type == "WHOLESALE" else "RETAIL",
        lines=lines,
        requested_date=row.scheduled_on,
        delivery_address=plan.delivery_address,
        customer_reference=plan.name[:64],
        notes=plan.notes or None,
        confirm=False,
        user_id=data.user_id,
        source="reorder",
        channel_ref=str(row.id),
    )
    try:
        order = sales_order_service.create_order(db, principal, payload)
    except IntegrityError:
        db.rollback()
        order = sales_order_service.get_order(db, principal, row.id)
        row = _occurrence(db, occurrence_id, lock=True)
    row.sales_order_id = order.id
    row.status = "ORDERED"
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_occurrence.order",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        user=principal.user,
        new_values={"sales_order_id": str(order.id)},
    )
    db.commit()
    _forget_summary()
    return order


def link_order(db: Session, principal: Principal, occurrence_id: uuid.UUID, data: LinkOrderIn) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id, lock=True)
    if row.sales_order_id is not None and row.sales_order_id != data.sales_order_id:
        raise ApiError(409, "already_ordered", "This reminder is already linked to an order.")
    order = db.get(SalesOrder, data.sales_order_id)
    if order is None or order.customer_id != row.plan.customer_id:
        raise ApiError(404, "not_found", "That order is not for this customer.")
    taken = db.scalar(
        select(CustomerReorderOccurrence.id).where(
            CustomerReorderOccurrence.sales_order_id == order.id,
            CustomerReorderOccurrence.id != row.id,
        )
    )
    if taken is not None:
        raise ApiError(409, "already_ordered", "That order is already linked to another reminder.")
    row.sales_order_id = order.id
    if row.status in OPEN:
        row.status = "ORDERED"
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_occurrence.link",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        user=principal.user,
        new_values={"sales_order_id": str(order.id)},
    )
    db.commit()
    _forget_summary()
    return _one(db, row.id)


def complete(db: Session, principal: Principal, occurrence_id: uuid.UUID) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id, lock=True)
    if row.sales_order_id is None:
        raise ApiError(409, "order_required", "Link or create the order before marking the delivery complete.")
    if row.status == "SKIPPED":
        raise ApiError(409, "occurrence_closed", "A skipped reminder cannot be marked delivered.")
    row.status = "DELIVERED"
    row.completed_at = datetime.now(UTC)
    audit.record(
        db,
        action_type="UPDATE",
        action="reorder_occurrence.complete",
        target_entity="CustomerReorderOccurrence",
        target_entity_id=row.id,
        user=principal.user,
    )
    db.commit()
    _forget_summary()
    return _one(db, row.id)


def _occurrence(db: Session, occurrence_id: uuid.UUID, *, lock: bool = False) -> CustomerReorderOccurrence:
    stmt = (
        select(CustomerReorderOccurrence)
        .where(CustomerReorderOccurrence.id == occurrence_id)
        .options(
            selectinload(CustomerReorderOccurrence.plan).selectinload(CustomerReorderPlan.items),
            selectinload(CustomerReorderOccurrence.plan).selectinload(CustomerReorderPlan.customer),
        )
    )
    if lock:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise ApiError(404, "not_found", "Reorder reminder was not found.")
    return row


def _one(db: Session, occurrence_id: uuid.UUID) -> OccurrenceOut:
    row = _occurrence(db, occurrence_id)
    stock = _availability(db, [item.product_id for item in row.plan.items], row.plan.store_id)
    return occurrence_out(db, row, _messages(db, [row]), stock)


def _messages(db: Session, rows: list[CustomerReorderOccurrence]) -> dict[str, OutboundMessage]:
    keys = [NOTIFY_KEY.format(row.id) for row in rows]
    if not keys:
        return {}
    found = db.scalars(select(OutboundMessage).where(OutboundMessage.dedupe_key.in_(keys))).all()
    return {message.dedupe_key: message for message in found if message.dedupe_key}


def plan_out(db: Session, plan: CustomerReorderPlan) -> PlanOut:
    stock = _availability(db, [item.product_id for item in plan.items], plan.store_id)
    products = _products(db, plan.items)
    salesperson = db.get(User, plan.salesperson_id) if plan.salesperson_id else None
    customer = plan.customer
    return PlanOut(
        id=plan.id,
        customer_id=plan.customer_id,
        customer_name=customer.name if customer else "",
        customer_code=customer.code if customer else "",
        name=plan.name,
        frequency=plan.frequency,  # type: ignore[arg-type]
        weekdays=list(plan.weekdays or []),
        month_day=plan.month_day,
        start_on=plan.start_on,
        end_on=plan.end_on,
        next_on=plan.next_on,
        preferred_time=plan.preferred_time,
        timezone=plan.timezone,
        lead_days=plan.lead_days,
        fulfillment=plan.fulfillment,  # type: ignore[arg-type]
        delivery_address=plan.delivery_address,
        notes=plan.notes,
        status=plan.status,  # type: ignore[arg-type]
        salesperson_id=plan.salesperson_id,
        salesperson_name=salesperson.full_name if salesperson else None,
        store_id=plan.store_id,
        notify_customer=plan.notify_customer,
        items=[_item_out(db, item, products, stock) for item in plan.items],
        created_at=plan.created_at,
        updated_at=plan.updated_at,
    )


def occurrence_out(
    db: Session,
    row: CustomerReorderOccurrence,
    messages: dict[str, OutboundMessage],
    stock: dict[uuid.UUID, int],
) -> OccurrenceOut:
    plan = row.plan
    customer = plan.customer
    products = _products(db, plan.items)
    salesperson = db.get(User, plan.salesperson_id) if plan.salesperson_id else None
    order = row.sales_order
    message = messages.get(NOTIFY_KEY.format(row.id))
    visible = row.status
    if visible == "SNOOZED" and row.snooze_until is not None and row.snooze_until <= datetime.now(UTC):
        visible = "PENDING"
    return OccurrenceOut(
        id=row.id,
        plan_id=plan.id,
        plan_name=plan.name,
        customer_id=plan.customer_id,
        customer_name=customer.name if customer else "",
        customer_code=customer.code if customer else "",
        customer_active=bool(customer and customer.is_active),
        balance_cents=customer.current_balance_cents if customer else 0,
        scheduled_on=row.scheduled_on,
        preferred_time=plan.preferred_time,
        timezone=plan.timezone,
        status=visible,  # type: ignore[arg-type]
        fulfillment=plan.fulfillment,  # type: ignore[arg-type]
        delivery_address=plan.delivery_address,
        salesperson_name=salesperson.full_name if salesperson else None,
        store_id=plan.store_id,
        items=[_item_out(db, item, products, stock) for item in plan.items],
        stock_note=row.stock_note,
        sales_order_id=row.sales_order_id,
        sales_order_number=order.number if order else None,
        sales_order_status=order.status if order else None,
        notification_status=message.status if message is not None else row.notification_status,
        notification_error=(message.last_error if message is not None else row.notification_error),
        snooze_until=row.snooze_until,
        skip_reason=row.skip_reason,
        overdue=row.status in OPEN and row.scheduled_on < local_today(plan.timezone),
        created_at=row.created_at,
        completed_at=row.completed_at,
    )


def _products(db: Session, items: list[CustomerReorderPlanItem]) -> dict[uuid.UUID, Product]:
    ids = {item.product_id for item in items}
    if not ids:
        return {}
    return {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(ids))).all()}


def _item_out(
    db: Session,
    item: CustomerReorderPlanItem,
    products: dict[uuid.UUID, Product],
    stock: dict[uuid.UUID, int],
) -> PlanItemOut:
    product = products.get(item.product_id)
    factor = uom_service.factor_of(db, item.unit) or 1
    return PlanItemOut(
        id=item.id,
        product_id=item.product_id,
        product_name=product.name if product else "Discontinued product",
        sku=product.sku if product else "",
        quantity=item.quantity,
        unit=item.unit,
        unit_factor=factor,
        base_quantity=item.quantity * factor,
        note=item.note,
        available=stock.get(item.product_id) if product and product.is_stock_tracked else None,
        discontinued=product is None,
    )

