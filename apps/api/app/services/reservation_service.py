"""Reservations for restaurant and cafe branches.

Bookings, seating, and the table timeline live beside the existing dining tables and open orders.
A reservation always has a customer. A confirmed booking always has a table. Overlap is rejected
in this transaction, and on PostgreSQL the table row is locked so two registers cannot take it together.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.messaging import OutboundMessage
from app.models.reservation import (
    CANCEL_REASONS,
    Reservation,
    ReservationSettings,
    ReservationStatusEvent,
    SeatingSessionOrder,
    TableActivityEvent,
    TableSeatingSession,
)
from app.models.restaurant import DiningArea, DiningTable, OpenOrder
from app.models.store import Store
from app.models.user import User
from app.schemas.reservations import (
    ActivityEventOut,
    AvailabilityOut,
    AvailabilityTable,
    CancelReservation,
    CustomerPick,
    NoShowReservation,
    RejectReservation,
    ReleaseTable,
    ReservationCreate,
    ReservationCustomerIn,
    ReservationOut,
    ReservationSettingsIn,
    ReservationSettingsOut,
    ReservationUpdate,
    SeatResult,
    StatusEventOut,
    TableHistoryOut,
    WalkInCreate,
)
from app.schemas.wholesale import CustomerWrite
from app.services import audit
from app.services.customer_service import new_customer
from app.services.settings_service import load_settings
from app.tenancy.scoping import active_tenant_id

PROFILES = frozenset({"restaurant", "cafe"})
ACTIVE = ("pending", "confirmed", "arrived", "seated")
TRANSITIONS: dict[str, set[str]] = {
    "pending": {"confirmed", "cancelled", "rejected"},
    "confirmed": {"arrived", "cancelled", "no_show"},
    "arrived": {"seated", "cancelled", "no_show"},
    "seated": {"completed"},
    "completed": set(),
    "cancelled": set(),
    "no_show": set(),
    "rejected": set(),
}
_NOTICE = {
    "confirmed": ("reservation_confirmed", "notify_confirmation"),
    "updated": ("reservation_updated", "notify_updates"),
    "cancelled": ("reservation_cancelled", "notify_cancellation"),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    """SQLite gives back naive timestamps. Treat those as UTC."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ApiError(422, "invalid_request", f"{label} must include a timezone.")
    return value.astimezone(UTC)


def _actor(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


def _profile(db: Session) -> str:
    return load_settings(db).business_profile or ""


def _reservations_open(db: Session) -> bool:
    return _profile(db) in PROFILES


def _require_profile(db: Session) -> None:
    if not _reservations_open(db):
        raise ApiError(403, "reservations_unavailable", "Table reservations are for restaurant and cafe businesses.")


def scope_store(principal: Principal, store_id: uuid.UUID, *, history: bool = False) -> None:
    if principal.store_id is None or principal.store_id == store_id:
        return
    needed = Permission.TABLE_HISTORY_VIEW_ALL if history else Permission.RESERVATIONS_VIEW_ALL
    if needed.value not in principal.permissions and principal.kind != "device":
        raise ApiError(403, "store_scope", "You can only work reservations in your own branch.")
    if principal.kind == "device" and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only work reservations in your own branch.")


def _settings(db: Session, store_id: uuid.UUID) -> ReservationSettings | None:
    return db.scalar(select(ReservationSettings).where(ReservationSettings.store_id == store_id))


def _policy(db: Session, store_id: uuid.UUID) -> ReservationSettings:
    row = _settings(db, store_id)
    if row is not None:
        return row
    # Column defaults apply on insert, not on a plain instance, so spell them out here.
    return ReservationSettings(
        store_id=store_id,
        enabled=True,
        duration_minutes=90,
        buffer_minutes=15,
        grace_minutes=15,
        min_notice_minutes=0,
        max_advance_days=30,
        max_guests=20,
        allow_same_day=True,
        allow_walk_in=True,
        allow_guest_profiles=False,
        require_phone=False,
        confirm_on_create=True,
        notify_confirmation=True,
        notify_updates=True,
        notify_cancellation=True,
        notify_reminder=False,
        open_time="09:00",
        close_time="23:00",
        timezone="Asia/Dubai",
    )


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ApiError(422, "invalid_request", "That timezone is not recognized.") from exc


def _clock(value: str) -> tuple[int, int]:
    hour, minute = value.split(":")
    return int(hour), int(minute)


def settings_out(db: Session, principal: Principal, store_id: uuid.UUID) -> ReservationSettingsOut:
    _require_profile(db)
    scope_store(principal, store_id)
    row = _policy(db, store_id)
    return ReservationSettingsOut(
        store_id=store_id,
        enabled=row.enabled,
        duration_minutes=row.duration_minutes,
        buffer_minutes=row.buffer_minutes,
        grace_minutes=row.grace_minutes,
        min_notice_minutes=row.min_notice_minutes,
        max_advance_days=row.max_advance_days,
        max_guests=row.max_guests,
        allow_same_day=row.allow_same_day,
        allow_walk_in=row.allow_walk_in,
        allow_guest_profiles=row.allow_guest_profiles,
        require_phone=row.require_phone,
        confirm_on_create=row.confirm_on_create,
        notify_confirmation=row.notify_confirmation,
        notify_updates=row.notify_updates,
        notify_cancellation=row.notify_cancellation,
        notify_reminder=row.notify_reminder,
        open_time=row.open_time,
        close_time=row.close_time,
        timezone=row.timezone,
    )


def save_settings(
    db: Session, principal: Principal, store_id: uuid.UUID, data: ReservationSettingsIn
) -> ReservationSettingsOut:
    _require_profile(db)
    scope_store(principal, store_id)
    if db.get(Store, store_id) is None:
        raise ApiError(404, "not_found", "That branch was not found.")
    _zone(data.timezone)
    if _clock(data.close_time) <= _clock(data.open_time):
        raise ApiError(422, "invalid_request", "Closing time has to be later than opening time on the same day.")
    row = _settings(db, store_id)
    if row is None:
        row = ReservationSettings(store_id=store_id)
        db.add(row)
    for name, value in data.model_dump().items():
        setattr(row, name, value)
    db.commit()
    db.refresh(row)
    return settings_out(db, principal, store_id)


def search_customers(db: Session, principal: Principal, store_id: uuid.UUID, query: str) -> list[CustomerPick]:
    _require_profile(db)
    scope_store(principal, store_id)
    text = query.strip()
    if len(text) < 2:
        return []
    like = f"%{text}%"
    rows = db.scalars(
        select(Customer)
        .where(
            Customer.is_active.is_(True),
            or_(
                Customer.name.ilike(like),
                Customer.phone.ilike(like),
                Customer.email.ilike(like),
                Customer.code.ilike(like),
            ),
        )
        .order_by(Customer.name)
        .limit(20)
    )
    return [CustomerPick(id=row.id, code=row.code, name=row.name, phone=row.phone, email=row.email) for row in rows]


def _table(db: Session, table_id: uuid.UUID, store_id: uuid.UUID, *, lock: bool) -> tuple[DiningTable, DiningArea]:
    stmt = select(DiningTable).where(DiningTable.id == table_id)
    bind = db.get_bind()
    if lock and bind is not None and bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    table = db.scalars(stmt).one_or_none()
    area = db.get(DiningArea, table.area_id) if table is not None else None
    if table is None or area is None or area.store_id != store_id:
        raise ApiError(422, "invalid_table", "Choose a table in this branch.")
    if not table.is_active or not area.is_active:
        raise ApiError(422, "invalid_table", "That table is not available.")
    return table, area


def _employee(db: Session, user_id: uuid.UUID | None, store_id: uuid.UUID) -> None:
    if user_id is None:
        return
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise ApiError(422, "invalid_request", "That employee was not found.")
    if user.store_id is not None and user.store_id != store_id:
        raise ApiError(403, "store_scope", "That employee is not assigned to this branch.")


def _contact(customer: Customer, policy: ReservationSettings, *, advance: bool) -> None:
    phone = (customer.phone or "").strip()
    email = (customer.email or "").strip()
    if email and "@" not in email:
        raise ApiError(422, "invalid_request", "Enter a valid email address.")
    guest_only = (not advance) and policy.allow_guest_profiles
    if guest_only:
        return
    if policy.require_phone and not phone:
        raise ApiError(422, "contact_required", "This reservation needs a phone number.")
    if not phone and not email:
        raise ApiError(422, "contact_required", "Add a phone number or an email address.")


def _resolve_customer(
    db: Session,
    policy: ReservationSettings,
    *,
    customer_id: uuid.UUID | None,
    incoming: ReservationCustomerIn | None,
    advance: bool,
) -> Customer:
    if customer_id is None and incoming is None:
        raise ApiError(422, "customer_required", "Choose a customer or add one. Anonymous reservations are not kept.")
    if customer_id is not None and incoming is not None:
        raise ApiError(422, "invalid_request", "Choose an existing customer or a new one, not both.")
    if customer_id is not None:
        customer = db.get(Customer, customer_id)
        if customer is None or not customer.is_active:
            raise ApiError(422, "customer_required", "That customer was not found.")
    else:
        assert incoming is not None
        customer = new_customer(
            db,
            CustomerWrite(
                name=incoming.name.strip(),
                phone=(incoming.phone or "").strip() or None,
                email=(incoming.email or "").strip() or None,
            ),
        )
        db.flush()
    _contact(customer, policy, advance=advance)
    return customer


def _rules(
    policy: ReservationSettings,
    starts_at: datetime,
    guest_count: int,
    seats: int | None,
    *,
    override_reason: str | None,
    allow_override: bool,
) -> str | None:
    zone = _zone(policy.timezone)
    local = starts_at.astimezone(zone)
    now_local = _now().astimezone(zone)
    problems: list[str] = []
    open_h, open_m = _clock(policy.open_time)
    close_h, close_m = _clock(policy.close_time)
    minutes = local.hour * 60 + local.minute
    if minutes < open_h * 60 + open_m or minutes >= close_h * 60 + close_m:
        problems.append(f"Reservations are taken between {policy.open_time} and {policy.close_time}.")
    if not policy.allow_same_day and local.date() == now_local.date():
        problems.append("Same-day reservations are switched off.")
    if starts_at < _now() + timedelta(minutes=policy.min_notice_minutes):
        problems.append("That time is sooner than the minimum notice.")
    if starts_at > _now() + timedelta(days=policy.max_advance_days):
        problems.append("That date is further ahead than this branch allows.")
    if guest_count > policy.max_guests:
        problems.append(f"This branch takes reservations of up to {policy.max_guests} guests.")
    if seats is not None and guest_count > seats:
        problems.append(f"That table seats {seats}.")
    if not problems:
        return None
    reason = (override_reason or "").strip()
    if not allow_override or len(reason) < 3:
        raise ApiError(422, "reservation_rules", problems[0])
    return reason


def _overlap(
    db: Session, table_id: uuid.UUID, starts_at: datetime, blocked_until: datetime, skip: uuid.UUID | None
) -> None:
    stmt = select(Reservation.id).where(
        Reservation.table_id == table_id,
        Reservation.status.in_(ACTIVE),
        Reservation.starts_at < blocked_until,
        Reservation.blocked_until > starts_at,
    )
    if skip is not None:
        stmt = stmt.where(Reservation.id != skip)
    if db.scalar(stmt.limit(1)) is not None:
        raise ApiError(409, "table_unavailable", "That table is already reserved for this time.")
    sitting = db.scalars(
        select(TableSeatingSession).where(
            TableSeatingSession.table_id == table_id,
            TableSeatingSession.status == "active",
        )
    ).all()
    for session in sitting:
        if session.reservation_id == skip:
            continue
        occupy_until = _now() + (blocked_until - starts_at)
        if session.started_at < blocked_until and occupy_until > starts_at:
            raise ApiError(409, "table_unavailable", "That table still has guests seated.")
    orders = db.scalars(select(OpenOrder).where(OpenOrder.table_id == table_id, OpenOrder.status == "OPEN")).all()
    for order in orders:
        occupy_until = _now() + (blocked_until - starts_at)
        opened = order.opened_at if order.opened_at.tzinfo is not None else order.opened_at.replace(tzinfo=UTC)
        if opened < blocked_until and occupy_until > starts_at:
            linked = db.scalar(select(SeatingSessionOrder).where(SeatingSessionOrder.order_id == order.id))
            if linked is not None and skip is not None:
                owner = db.get(TableSeatingSession, linked.seating_session_id)
                if owner is not None and owner.reservation_id == skip:
                    continue
            raise ApiError(409, "table_unavailable", "That table has an open order.")


def _note(
    db: Session,
    *,
    store_id: uuid.UUID,
    table_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    reservation_id: uuid.UUID | None,
    seating_session_id: uuid.UUID | None,
    order_id: uuid.UUID | None,
    event_type: str,
    description: str,
    actor_id: uuid.UUID | None,
    metadata: dict | None = None,
) -> None:
    if table_id is None:
        return
    db.add(
        TableActivityEvent(
            store_id=store_id,
            table_id=table_id,
            customer_id=customer_id,
            reservation_id=reservation_id,
            seating_session_id=seating_session_id,
            order_id=order_id,
            event_type=event_type,
            description=description[:300],
            actor_user_id=actor_id,
            event_metadata=metadata,
        )
    )


def _status_event(
    db: Session,
    row: Reservation,
    previous: str | None,
    status: str,
    actor_id: uuid.UUID | None,
    reason: str | None,
) -> None:
    db.add(
        ReservationStatusEvent(
            store_id=row.store_id,
            reservation_id=row.id,
            previous_status=previous,
            status=status,
            reason=(reason or None),
            actor_user_id=actor_id,
        )
    )


def _move(db: Session, row: Reservation, status: str, actor_id: uuid.UUID | None, reason: str | None) -> None:
    if status not in TRANSITIONS[row.status]:
        raise ApiError(409, "invalid_transition", f"A {row.status} reservation cannot move to {status}.")
    previous = row.status
    row.status = status
    _status_event(db, row, previous, status, actor_id, reason)
    _note(
        db,
        store_id=row.store_id,
        table_id=row.table_id,
        customer_id=row.customer_id,
        reservation_id=row.id,
        seating_session_id=None,
        order_id=None,
        event_type=f"reservation_{status}",
        description=f"Reservation {row.reservation_number} {status.replace('_', ' ')}.",
        actor_id=actor_id,
        metadata={"previous": previous, "reason": reason},
    )


def _active_session(db: Session, table_id: uuid.UUID) -> TableSeatingSession | None:
    return db.scalar(
        select(TableSeatingSession)
        .where(TableSeatingSession.table_id == table_id, TableSeatingSession.status == "active")
        .order_by(TableSeatingSession.started_at.desc())
        .limit(1)
    )


def _link(db: Session, session: TableSeatingSession, order: OpenOrder) -> None:
    existing = db.scalar(select(SeatingSessionOrder).where(SeatingSessionOrder.order_id == order.id))
    if existing is None:
        db.add(SeatingSessionOrder(seating_session_id=session.id, order_id=order.id))


def _live(order: OpenOrder) -> bool:
    return any(item.voided_at is None for item in order.items)


def _publish(store_id: uuid.UUID, table_id: uuid.UUID | None, kind: str, reservation_id: uuid.UUID | None) -> None:
    from app.websockets.table_sync import publish

    publish(
        store_id,
        {
            "type": "RESERVATION_CHANGED",
            "store_id": str(store_id),
            "table_id": str(table_id) if table_id is not None else None,
            "reservation_id": str(reservation_id) if reservation_id is not None else None,
            "status": kind,
        },
    )


def _notification(db: Session, row: Reservation) -> tuple[str, str | None]:
    if row.notification_message_id is None:
        return row.notification_status, row.notification_detail
    message = db.get(OutboundMessage, row.notification_message_id)
    if message is None:
        return row.notification_status, row.notification_detail
    mapped = {"QUEUED": "pending", "SENT": "sent", "FAILED": "failed", "SKIPPED": "skipped"}.get(
        message.status, row.notification_status
    )
    return mapped, message.last_error or row.notification_detail


def _out(db: Session, row: Reservation, *, with_events: bool) -> ReservationOut:
    customer = db.get(Customer, row.customer_id)
    table = db.get(DiningTable, row.table_id) if row.table_id is not None else None
    area = db.get(DiningArea, table.area_id) if table is not None else None
    status, detail = _notification(db, row)
    order_id = None
    sitting = db.scalar(
        select(TableSeatingSession)
        .where(TableSeatingSession.reservation_id == row.id)
        .order_by(TableSeatingSession.started_at.desc())
        .limit(1)
    )
    if sitting is not None:
        order_id = db.scalar(
            select(SeatingSessionOrder.order_id)
            .where(SeatingSessionOrder.seating_session_id == sitting.id)
            .order_by(SeatingSessionOrder.created_at.desc())
            .limit(1)
        )
    events: list[StatusEventOut] = []
    if with_events:
        events = [
            StatusEventOut(
                id=item.id,
                previous_status=item.previous_status,
                status=item.status,
                reason=item.reason,
                actor_user_id=item.actor_user_id,
                created_at=item.created_at,
            )
            for item in db.scalars(
                select(ReservationStatusEvent)
                .where(ReservationStatusEvent.reservation_id == row.id)
                .order_by(ReservationStatusEvent.created_at)
            )
        ]
    assert customer is not None
    return ReservationOut(
        id=row.id,
        reservation_number=row.reservation_number,
        store_id=row.store_id,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_email=customer.email,
        table_id=table.id if table is not None else None,
        table_label=table.label if table is not None else None,
        area_name=area.name if area is not None else None,
        guest_count=row.guest_count,
        status=row.status,  # type: ignore[arg-type]
        source=row.source,
        occasion=row.occasion,
        special_requests=row.special_requests,
        internal_notes=row.internal_notes,
        assigned_employee_id=row.assigned_employee_id,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        expected_arrival_at=row.expected_arrival_at,
        confirmed_at=row.confirmed_at,
        arrived_at=row.arrived_at,
        seated_at=row.seated_at,
        cancelled_at=row.cancelled_at,
        cancellation_reason=row.cancellation_reason,
        customer_notified=row.customer_notified,
        notification_status=status,
        notification_detail=detail,
        order_id=order_id,
        events=events,
    )


def _number(db: Session, store_id: uuid.UUID) -> str:
    highest = db.scalar(select(func.count()).select_from(Reservation).where(Reservation.store_id == store_id))
    return f"R-{int(highest or 0) + 1:05d}"


def _queue(db: Session, row: Reservation, kind: str) -> None:
    spec = _NOTICE.get(kind)
    if spec is None:
        return
    template_key, flag = spec
    policy = _policy(db, row.store_id)
    if not getattr(policy, flag):
        row.notification_status = "skipped"
        row.notification_detail = "Notifications are switched off for this event."
        db.commit()
        return
    customer = db.get(Customer, row.customer_id)
    store = db.get(Store, row.store_id)
    table = db.get(DiningTable, row.table_id) if row.table_id is not None else None
    if customer is None:
        return
    reservation_id = row.id
    try:
        from app.services.messaging_service import enqueue

        message = enqueue(
            db,
            template_key=template_key,
            customer=customer,
            context={
                "when": row.starts_at.isoformat(),
                "table": table.label if table is not None else "to be assigned",
                "guests": str(row.guest_count),
                "store": store.name if store is not None else "",
                "number": row.reservation_number,
            },
            dedupe_key=f"{template_key}:{row.id}",
        )
    except Exception:
        db.rollback()
        return
    fresh = db.get(Reservation, reservation_id)
    if fresh is None:
        return
    if message is None:
        fresh.notification_status = "skipped"
        fresh.notification_detail = "No message was queued."
    else:
        fresh.notification_message_id = message.id
        fresh.notification_status = "skipped" if message.status == "SKIPPED" else "pending"
        fresh.notification_detail = message.last_error
    try:
        db.commit()
    except Exception:
        db.rollback()


def list_reservations(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    status: str | None,
    table_id: uuid.UUID | None,
    customer_id: uuid.UUID | None,
    employee_id: uuid.UUID | None,
    area_id: uuid.UUID | None,
    starts_from: datetime | None,
    starts_to: datetime | None,
) -> list[ReservationOut]:
    _require_profile(db)
    scope_store(principal, store_id)
    stmt = select(Reservation).where(Reservation.store_id == store_id, Reservation.tenant_id == active_tenant_id())
    if status is not None:
        stmt = stmt.where(Reservation.status == status)
    if table_id is not None:
        stmt = stmt.where(Reservation.table_id == table_id)
    if customer_id is not None:
        stmt = stmt.where(Reservation.customer_id == customer_id)
    if employee_id is not None:
        stmt = stmt.where(Reservation.assigned_employee_id == employee_id)
    if area_id is not None:
        stmt = stmt.join(DiningTable, DiningTable.id == Reservation.table_id).where(DiningTable.area_id == area_id)
    if starts_from is not None:
        stmt = stmt.where(Reservation.starts_at >= _aware(starts_from, "From"))
    if starts_to is not None:
        stmt = stmt.where(Reservation.starts_at < _aware(starts_to, "To"))
    rows = db.scalars(stmt.order_by(Reservation.starts_at).limit(200)).all()
    return [_out(db, row, with_events=False) for row in rows]


def get_reservation(db: Session, principal: Principal, reservation_id: uuid.UUID) -> ReservationOut:
    _require_profile(db)
    row = db.get(Reservation, reservation_id)
    if row is None or row.tenant_id != active_tenant_id():
        raise ApiError(404, "not_found", "That reservation was not found.")
    scope_store(principal, row.store_id)
    return _out(db, row, with_events=True)


def _span(
    policy: ReservationSettings, starts_at: datetime, duration: int | None
) -> tuple[datetime, datetime, datetime]:
    minutes = duration or policy.duration_minutes
    ends = starts_at + timedelta(minutes=minutes)
    blocked = ends + timedelta(minutes=policy.buffer_minutes)
    return starts_at, ends, blocked


def create_reservation(
    db: Session, principal: Principal, data: ReservationCreate, *, allow_override: bool
) -> ReservationOut:
    _require_profile(db)
    scope_store(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "That branch was not found.")
    policy = _policy(db, data.store_id)
    if not policy.enabled:
        raise ApiError(403, "reservations_disabled", "Reservations are switched off for this branch.")
    starts = _aware(data.starts_at, "Reservation time")
    arrival = _aware(data.expected_arrival_at, "Arrival time") if data.expected_arrival_at else None
    customer = _resolve_customer(
        db, policy, customer_id=data.customer_id, incoming=data.customer, advance=True
    )
    table = None
    seats = None
    if data.table_id is not None:
        table, _area = _table(db, data.table_id, data.store_id, lock=True)
        seats = table.seats
    override = _rules(
        policy, starts, data.guest_count, seats, override_reason=data.override_reason, allow_override=allow_override
    )
    starts, ends, blocked = _span(policy, starts, data.duration_minutes)
    if table is not None:
        _overlap(db, table.id, starts, blocked, None)
    _employee(db, data.assigned_employee_id, data.store_id)
    actor = _actor(principal)
    row = Reservation(
        store_id=data.store_id,
        customer_id=customer.id,
        table_id=table.id if table is not None else None,
        reservation_number=_number(db, data.store_id),
        starts_at=starts,
        ends_at=ends,
        blocked_until=blocked,
        expected_arrival_at=arrival,
        guest_count=data.guest_count,
        status="pending",
        source=data.source,
        occasion=(data.occasion or "").strip() or None,
        special_requests=(data.special_requests or "").strip() or None,
        internal_notes=(data.internal_notes or "").strip() or None,
        assigned_employee_id=data.assigned_employee_id,
        notification_status="pending",
    )
    db.add(row)
    try:
        with db.begin_nested():
            db.flush()
    except IntegrityError as exc:
        row.reservation_number = _number(db, data.store_id)
        try:
            with db.begin_nested():
                row.reservation_number = f"R-{uuid.uuid4().hex[:8].upper()}"
                db.flush()
        except IntegrityError:
            raise ApiError(409, "conflict", "Could not save that reservation. Try again.") from exc
    _status_event(db, row, None, "pending", actor, None)
    _note(
        db,
        store_id=row.store_id,
        table_id=row.table_id,
        customer_id=row.customer_id,
        reservation_id=row.id,
        seating_session_id=None,
        order_id=None,
        event_type="reservation_created",
        description=f"Reservation {row.reservation_number} created for {customer.name}.",
        actor_id=actor,
        metadata={"override": override} if override else None,
    )
    if override:
        audit.record(
            db,
            action_type="UPDATE",
            action="reservation.override",
            target_entity="Reservation",
            target_entity_id=row.id,
            store_id=row.store_id,
            user_id=actor,
            reason_notes=override,
        )
    notice = None
    if policy.confirm_on_create and table is not None:
        _move(db, row, "confirmed", actor, None)
        row.confirmed_at = _now()
        notice = "confirmed"
    else:
        row.notification_status = "skipped"
        row.notification_detail = "No confirmation message until the reservation is confirmed."
    db.commit()
    db.refresh(row)
    if notice:
        _queue(db, row, notice)
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def _get(db: Session, principal: Principal, reservation_id: uuid.UUID) -> Reservation:
    _require_profile(db)
    row = db.get(Reservation, reservation_id)
    if row is None or row.tenant_id != active_tenant_id():
        raise ApiError(404, "not_found", "That reservation was not found.")
    scope_store(principal, row.store_id)
    return row


def update_reservation(
    db: Session, principal: Principal, reservation_id: uuid.UUID, data: ReservationUpdate, *, allow_override: bool
) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    if row.status not in {"pending", "confirmed", "arrived"}:
        raise ApiError(409, "invalid_transition", "This reservation can no longer be edited.")
    policy = _policy(db, row.store_id)
    actor = _actor(principal)
    changes = data.model_dump(exclude_unset=True)
    table_id = changes.get("table_id", row.table_id)
    guest_count = changes.get("guest_count", row.guest_count)
    starts = _aware(changes["starts_at"], "Reservation time") if "starts_at" in changes else row.starts_at
    duration = changes.get("duration_minutes")
    if duration is None:
        duration = int((row.ends_at - row.starts_at).total_seconds() // 60)
    seats = None
    table = None
    if table_id is not None:
        table, _area = _table(db, table_id, row.store_id, lock=True)
        seats = table.seats
    sensitive = row.status == "arrived" and (
        ("table_id" in changes and changes["table_id"] != row.table_id)
        or ("customer_id" in changes and changes["customer_id"] not in (None, row.customer_id))
    )
    if sensitive and len((data.reason or "").strip()) < 3:
        raise ApiError(422, "reason_required", "Changing the table or customer after arrival needs a reason.")
    override = _rules(
        policy, starts, guest_count, seats, override_reason=data.override_reason, allow_override=allow_override
    )
    starts, ends, blocked = _span(policy, starts, duration)
    if table is not None:
        _overlap(db, table.id, starts, blocked, row.id)
    if "customer_id" in changes and changes["customer_id"] is not None:
        customer = _resolve_customer(db, policy, customer_id=changes["customer_id"], incoming=None, advance=True)
        row.customer_id = customer.id
    if "assigned_employee_id" in changes:
        _employee(db, changes["assigned_employee_id"], row.store_id)
        row.assigned_employee_id = changes["assigned_employee_id"]
    row.table_id = table.id if table is not None else None
    row.starts_at = starts
    row.ends_at = ends
    row.blocked_until = blocked
    row.guest_count = guest_count
    if "expected_arrival_at" in changes:
        row.expected_arrival_at = (
            _aware(changes["expected_arrival_at"], "Arrival time") if changes["expected_arrival_at"] else None
        )
    for field in ("special_requests", "occasion", "internal_notes"):
        if field in changes:
            setattr(row, field, (changes[field] or "").strip() or None)
    _note(
        db,
        store_id=row.store_id,
        table_id=row.table_id,
        customer_id=row.customer_id,
        reservation_id=row.id,
        seating_session_id=None,
        order_id=None,
        event_type="reservation_updated",
        description=f"Reservation {row.reservation_number} updated.",
        actor_id=actor,
        metadata={"reason": data.reason, "override": override},
    )
    if sensitive or override:
        audit.record(
            db,
            action_type="UPDATE",
            action="reservation.update",
            target_entity="Reservation",
            target_entity_id=row.id,
            store_id=row.store_id,
            user_id=actor,
            reason_notes=data.reason or override,
        )
    db.commit()
    db.refresh(row)
    _queue(db, row, "updated")
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def confirm(db: Session, principal: Principal, reservation_id: uuid.UUID) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    if row.table_id is None:
        raise ApiError(422, "invalid_table", "Assign a table before confirming.")
    _table(db, row.table_id, row.store_id, lock=True)
    _overlap(db, row.table_id, row.starts_at, row.blocked_until, row.id)
    actor = _actor(principal)
    _move(db, row, "confirmed", actor, None)
    row.confirmed_at = _now()
    db.commit()
    db.refresh(row)
    _queue(db, row, "confirmed")
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def arrive(db: Session, principal: Principal, reservation_id: uuid.UUID) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    actor = _actor(principal)
    _move(db, row, "arrived", actor, None)
    row.arrived_at = _now()
    _note(
        db,
        store_id=row.store_id,
        table_id=row.table_id,
        customer_id=row.customer_id,
        reservation_id=row.id,
        seating_session_id=None,
        order_id=None,
        event_type="customer_arrived",
        description="Customer arrived.",
        actor_id=actor,
    )
    db.commit()
    db.refresh(row)
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def _open_order(db: Session, table_id: uuid.UUID) -> OpenOrder | None:
    return db.scalar(
        select(OpenOrder)
        .where(OpenOrder.table_id == table_id, OpenOrder.status == "OPEN")
        .order_by(OpenOrder.opened_at.desc())
        .limit(1)
    )


def _server(db: Session, principal: Principal, employee_id: uuid.UUID | None, store_id: uuid.UUID) -> uuid.UUID:
    if principal.user is not None:
        return principal.user.id
    if employee_id is not None:
        return employee_id
    user = db.scalar(
        select(User)
        .where(
            User.is_active.is_(True),
            User.has_pos_access.is_(True),
            or_(User.store_id.is_(None), User.store_id == store_id),
        )
        .limit(1)
    )
    if user is None:
        raise ApiError(422, "invalid_request", "A signed-in employee has to seat the table.")
    return user.id


def _place(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    table: DiningTable,
    customer: Customer,
    guest_count: int,
    employee_id: uuid.UUID | None,
    reservation: Reservation | None,
) -> tuple[TableSeatingSession, OpenOrder]:
    if _active_session(db, table.id) is not None:
        raise ApiError(409, "table_unavailable", "That table already has guests seated.")
    actor = _actor(principal)
    sitting = TableSeatingSession(
        store_id=store_id,
        table_id=table.id,
        customer_id=customer.id,
        reservation_id=reservation.id if reservation is not None else None,
        guest_count=guest_count,
        assigned_employee_id=employee_id,
        status="active",
        started_at=_now(),
    )
    db.add(sitting)
    db.flush()
    order = _open_order(db, table.id)
    if order is not None and order.customer_id is not None and order.customer_id != customer.id:
        raise ApiError(409, "table_unavailable", "That table has an open order for someone else.")
    if order is None:
        from app.schemas.orders import OrderCreate
        from app.services import order_service

        created = order_service.create_order(
            db,
            principal,
            OrderCreate(
                id=uuid.uuid4(),
                store_id=store_id,
                service_type="DINE_IN",
                table_id=table.id,
                covers=guest_count,
                name=customer.name[:80],
                customer_id=customer.id,
                user_id=_server(db, principal, employee_id, store_id),
            ),
            commit=False,
        )
        order = db.get(OpenOrder, created.id)
    else:
        order.customer_id = customer.id
        order.name = customer.name[:80]
        order.covers = guest_count
        _link(db, sitting, order)
    assert order is not None
    _note(
        db,
        store_id=store_id,
        table_id=table.id,
        customer_id=customer.id,
        reservation_id=reservation.id if reservation is not None else None,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="customer_attached",
        description=f"{customer.name} attached to {table.label}.",
        actor_id=actor,
    )
    if employee_id is not None:
        _note(
            db,
            store_id=store_id,
            table_id=table.id,
            customer_id=customer.id,
            reservation_id=reservation.id if reservation is not None else None,
            seating_session_id=sitting.id,
            order_id=order.id,
            event_type="waiter_assigned",
            description="Waiter assigned.",
            actor_id=actor,
        )
    return sitting, order


def seat(db: Session, principal: Principal, reservation_id: uuid.UUID) -> SeatResult:
    row = _get(db, principal, reservation_id)
    if row.status != "arrived":
        raise ApiError(409, "invalid_transition", "Mark the customer arrived before seating them.")
    if row.table_id is None:
        raise ApiError(422, "invalid_table", "Assign a table before seating.")
    table, _area = _table(db, row.table_id, row.store_id, lock=True)
    customer = db.get(Customer, row.customer_id)
    if customer is None:
        raise ApiError(422, "customer_required", "This reservation has no customer.")
    actor = _actor(principal)
    sitting, order = _place(
        db,
        principal,
        store_id=row.store_id,
        table=table,
        customer=customer,
        guest_count=row.guest_count,
        employee_id=row.assigned_employee_id,
        reservation=row,
    )
    row = db.get(Reservation, reservation_id)
    assert row is not None
    if row.status != "seated":
        _move(db, row, "seated", actor, None)
        row.seated_at = _now()
    _note(
        db,
        store_id=row.store_id,
        table_id=table.id,
        customer_id=customer.id,
        reservation_id=row.id,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="customer_seated",
        description=f"{customer.name} seated at {table.label}.",
        actor_id=actor,
    )
    db.commit()
    _publish(row.store_id, table.id, "seated", row.id)
    return SeatResult(
        reservation_id=row.id,
        seating_session_id=sitting.id,
        order_id=order.id,
        table_id=table.id,
        table_label=table.label,
        customer_id=customer.id,
        customer_name=customer.name,
        guest_count=row.guest_count,
    )


def walk_in(db: Session, principal: Principal, data: WalkInCreate) -> SeatResult:
    _require_profile(db)
    scope_store(principal, data.store_id)
    policy = _policy(db, data.store_id)
    if not policy.allow_walk_in:
        raise ApiError(403, "walk_in_disabled", "Walk-ins are switched off for this branch.")
    customer = _resolve_customer(
        db, policy, customer_id=data.customer_id, incoming=data.customer, advance=False
    )
    table, _area = _table(db, data.table_id, data.store_id, lock=True)
    if data.guest_count > table.seats or data.guest_count > policy.max_guests:
        raise ApiError(422, "reservation_rules", f"That table seats {table.seats}.")
    starts = _now()
    _overlap(db, table.id, starts, starts + timedelta(minutes=policy.duration_minutes + policy.buffer_minutes), None)
    _employee(db, data.assigned_employee_id, data.store_id)
    sitting, order = _place(
        db,
        principal,
        store_id=data.store_id,
        table=table,
        customer=customer,
        guest_count=data.guest_count,
        employee_id=data.assigned_employee_id,
        reservation=None,
    )
    _note(
        db,
        store_id=data.store_id,
        table_id=table.id,
        customer_id=customer.id,
        reservation_id=None,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="walk_in_seated",
        description=f"Walk-in {customer.name} seated at {table.label}.",
        actor_id=_actor(principal),
    )
    db.commit()
    _publish(data.store_id, table.id, "walk_in", None)
    return SeatResult(
        reservation_id=None,
        seating_session_id=sitting.id,
        order_id=order.id,
        table_id=table.id,
        table_label=table.label,
        customer_id=customer.id,
        customer_name=customer.name,
        guest_count=data.guest_count,
    )


def cancel(db: Session, principal: Principal, reservation_id: uuid.UUID, data: CancelReservation) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    if data.reason not in CANCEL_REASONS:
        raise ApiError(422, "invalid_request", "Choose a cancellation reason.")
    if data.reason == "other" and len((data.explanation or "").strip()) < 3:
        raise ApiError(422, "reason_required", "Describe the other reason.")
    actor = _actor(principal)
    detail = (data.explanation or data.notes or "").strip() or None
    _move(db, row, "cancelled", actor, detail or data.reason)
    row.cancelled_at = _now()
    row.cancellation_reason = data.reason
    row.cancellation_detail = detail
    row.customer_notified = data.notified
    audit.record(
        db,
        action_type="UPDATE",
        action="reservation.cancel",
        target_entity="Reservation",
        target_entity_id=row.id,
        store_id=row.store_id,
        user_id=actor,
        reason_notes=detail or data.reason,
        details={"notified": data.notified},
    )
    db.commit()
    db.refresh(row)
    _queue(db, row, "cancelled")
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def mark_no_show(
    db: Session, principal: Principal, reservation_id: uuid.UUID, data: NoShowReservation
) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    policy = _policy(db, row.store_id)
    if _now() < _utc(row.starts_at) + timedelta(minutes=policy.grace_minutes):
        raise ApiError(409, "grace_period", "The arrival window has not ended.")
    actor = _actor(principal)
    _move(db, row, "no_show", actor, (data.notes or "").strip() or None)
    audit.record(
        db,
        action_type="UPDATE",
        action="reservation.no_show",
        target_entity="Reservation",
        target_entity_id=row.id,
        store_id=row.store_id,
        user_id=actor,
        reason_notes=data.notes,
    )
    db.commit()
    db.refresh(row)
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def reject(db: Session, principal: Principal, reservation_id: uuid.UUID, data: RejectReservation) -> ReservationOut:
    row = _get(db, principal, reservation_id)
    actor = _actor(principal)
    _move(db, row, "rejected", actor, data.reason.strip())
    db.commit()
    db.refresh(row)
    _publish(row.store_id, row.table_id, row.status, row.id)
    return _out(db, row, with_events=True)


def release(db: Session, principal: Principal, table_id: uuid.UUID, data: ReleaseTable) -> TableHistoryOut:
    _require_profile(db)
    table = db.get(DiningTable, table_id)
    area = db.get(DiningArea, table.area_id) if table is not None else None
    if table is None or area is None:
        raise ApiError(404, "not_found", "That table was not found.")
    scope_store(principal, area.store_id)
    sitting = _active_session(db, table.id)
    if sitting is None:
        raise ApiError(404, "no_session", "This table has no one seated.")
    orders = db.scalars(select(OpenOrder).where(OpenOrder.table_id == table.id, OpenOrder.status == "OPEN")).all()
    live = next((order for order in orders if _live(order)), None)
    reason = (data.reason or "").strip()
    actor = _actor(principal)
    if live is not None and len(reason) < 3:
        raise ApiError(422, "reason_required", "Releasing a table with an open order needs a reason.")
    sitting.status = "closed"
    sitting.ended_at = _now()
    reservation = db.get(Reservation, sitting.reservation_id) if sitting.reservation_id else None
    if live is None:
        for order in orders:
            order.status = "VOID"
            order.closed_at = _now()
        if reservation is not None and reservation.status == "seated":
            _move(db, reservation, "completed", actor, None)
        policy = _policy(db, area.store_id)
        _note(
            db,
            store_id=area.store_id,
            table_id=table.id,
            customer_id=sitting.customer_id,
            reservation_id=sitting.reservation_id,
            seating_session_id=sitting.id,
            order_id=orders[0].id if orders else None,
            event_type="table_released",
            description="Table released.",
            actor_id=actor,
        )
        _note(
            db,
            store_id=area.store_id,
            table_id=table.id,
            customer_id=sitting.customer_id,
            reservation_id=sitting.reservation_id,
            seating_session_id=sitting.id,
            order_id=None,
            event_type="table_cleaning",
            description=f"Table cleaning ({policy.buffer_minutes} min buffer before the next reservation).",
            actor_id=actor,
        )
        _note(
            db,
            store_id=area.store_id,
            table_id=table.id,
            customer_id=None,
            reservation_id=None,
            seating_session_id=None,
            order_id=None,
            event_type="table_available",
            description="Table marked available.",
            actor_id=actor,
        )
    else:
        audit.record(
            db,
            action_type="UPDATE",
            action="table.release_with_order",
            target_entity="DiningTable",
            target_entity_id=table.id,
            store_id=area.store_id,
            user_id=actor,
            reason_notes=reason,
            details={"order_id": str(live.id)},
        )
        _note(
            db,
            store_id=area.store_id,
            table_id=table.id,
            customer_id=sitting.customer_id,
            reservation_id=sitting.reservation_id,
            seating_session_id=sitting.id,
            order_id=live.id,
            event_type="table_released",
            description="Table released while an order is still open.",
            actor_id=actor,
            metadata={"reason": reason},
        )
    db.commit()
    _publish(area.store_id, table.id, "released", sitting.reservation_id)
    return history(db, principal, table.id, start=None, end=None)


def availability(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    starts_at: datetime,
    duration_minutes: int | None,
    guest_count: int,
) -> AvailabilityOut:
    _require_profile(db)
    scope_store(principal, store_id)
    policy = _policy(db, store_id)
    starts = _aware(starts_at, "Reservation time")
    _starts, ends, blocked = _span(policy, starts, duration_minutes)
    areas = db.scalars(select(DiningArea).where(DiningArea.store_id == store_id, DiningArea.is_active.is_(True))).all()
    tables: list[AvailabilityTable] = []
    for area in areas:
        found = db.scalars(
            select(DiningTable).where(DiningTable.area_id == area.id, DiningTable.is_active.is_(True))
        )
        for table in found:
            reason = None
            if guest_count > table.seats:
                reason = f"Seats {table.seats}"
            else:
                try:
                    _overlap(db, table.id, starts, blocked, None)
                except ApiError as exc:
                    reason = exc.message
            tables.append(
                AvailabilityTable(
                    table_id=table.id,
                    label=table.label,
                    area_name=area.name,
                    seats=table.seats,
                    available=reason is None,
                    reason=reason,
                )
            )
    return AvailabilityOut(starts_at=starts, ends_at=ends, tables=tables)


def history(
    db: Session,
    principal: Principal,
    table_id: uuid.UUID,
    *,
    start: datetime | None,
    end: datetime | None,
) -> TableHistoryOut:
    _require_profile(db)
    table = db.get(DiningTable, table_id)
    area = db.get(DiningArea, table.area_id) if table is not None else None
    if table is None or area is None:
        raise ApiError(404, "not_found", "That table was not found.")
    scope_store(principal, area.store_id, history=True)
    finish = _aware(end, "To") if end is not None else _now()
    begin = _aware(start, "From") if start is not None else finish - timedelta(hours=24)
    rows = db.scalars(
        select(TableActivityEvent)
        .where(
            TableActivityEvent.table_id == table.id,
            TableActivityEvent.store_id == area.store_id,
            TableActivityEvent.tenant_id == active_tenant_id(),
            TableActivityEvent.created_at >= begin,
            TableActivityEvent.created_at <= finish,
        )
        .order_by(TableActivityEvent.created_at, TableActivityEvent.id)
        .limit(500)
    ).all()
    return TableHistoryOut(
        table_id=table.id,
        table_label=table.label,
        starts_at=begin,
        ends_at=finish,
        events=[
            ActivityEventOut(
                id=item.id,
                store_id=item.store_id,
                table_id=item.table_id,
                customer_id=item.customer_id,
                reservation_id=item.reservation_id,
                seating_session_id=item.seating_session_id,
                order_id=item.order_id,
                event_type=item.event_type,
                description=item.description,
                actor_user_id=item.actor_user_id,
                created_at=item.created_at,
            )
            for item in rows
        ],
    )


def attach_order(db: Session, order: OpenOrder, incoming_customer_id: uuid.UUID | None) -> None:
    """Keep the seated customer when an offline register sends a different one."""
    if order.table_id is None or not _reservations_open(db):
        return
    sitting = _active_session(db, order.table_id)
    if sitting is None:
        return
    if incoming_customer_id is not None and incoming_customer_id != sitting.customer_id:
        order.customer_id = sitting.customer_id
        _note(
            db,
            store_id=order.store_id,
            table_id=order.table_id,
            customer_id=sitting.customer_id,
            reservation_id=sitting.reservation_id,
            seating_session_id=sitting.id,
            order_id=order.id,
            event_type="offline_conflict",
            description="The register sent a different customer. The seated customer was kept.",
            actor_id=None,
            metadata={"incoming_customer_id": str(incoming_customer_id)},
        )
    elif order.customer_id is None:
        order.customer_id = sitting.customer_id
    if not order.covers:
        order.covers = sitting.guest_count
    if not order.name:
        customer = db.get(Customer, sitting.customer_id)
        if customer is not None:
            order.name = customer.name[:80]
    _link(db, sitting, order)


def observe_order(
    db: Session,
    order: OpenOrder,
    kind: str,
    description: str,
    actor_id: uuid.UUID | None,
    *,
    discount_cents: int = 0,
) -> None:
    if order.table_id is None or not _reservations_open(db):
        return
    sitting = _active_session(db, order.table_id)
    if sitting is not None:
        _link(db, sitting, order)
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=order.customer_id or (sitting.customer_id if sitting is not None else None),
        reservation_id=sitting.reservation_id if sitting is not None else None,
        seating_session_id=sitting.id if sitting is not None else None,
        order_id=order.id,
        event_type=kind,
        description=description,
        actor_id=actor_id,
    )
    if discount_cents > 0:
        _note(
            db,
            store_id=order.store_id,
            table_id=order.table_id,
            customer_id=order.customer_id,
            reservation_id=sitting.reservation_id if sitting is not None else None,
            seating_session_id=sitting.id if sitting is not None else None,
            order_id=order.id,
            event_type="discount",
            description=f"Discount of {discount_cents} cents applied.",
            actor_id=actor_id,
        )
    if order.status not in {"SETTLED", "VOID"} or kind not in {"payment", "order_cancelled"}:
        return
    if sitting is None:
        return
    other = db.scalar(
        select(OpenOrder.id).where(
            OpenOrder.table_id == order.table_id,
            OpenOrder.status == "OPEN",
            OpenOrder.id != order.id,
        )
    )
    if other is not None:
        return
    sitting.status = "closed"
    sitting.ended_at = _now()
    reservation = db.get(Reservation, sitting.reservation_id) if sitting.reservation_id else None
    if reservation is not None and reservation.status == "seated":
        _move(db, reservation, "completed", actor_id, None)
    label = "Customer checkout completed." if order.status == "SETTLED" else "Order cancelled."
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=sitting.customer_id,
        reservation_id=sitting.reservation_id,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="checkout" if order.status == "SETTLED" else "order_cancelled",
        description=label,
        actor_id=actor_id,
    )
    policy = _policy(db, order.store_id)
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=sitting.customer_id,
        reservation_id=sitting.reservation_id,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="table_released",
        description="Table released.",
        actor_id=actor_id,
    )
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=None,
        reservation_id=None,
        seating_session_id=sitting.id,
        order_id=None,
        event_type="table_cleaning",
        description=f"Table cleaning ({policy.buffer_minutes} min buffer).",
        actor_id=actor_id,
    )
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=None,
        reservation_id=None,
        seating_session_id=None,
        order_id=None,
        event_type="table_available",
        description="Table marked available.",
        actor_id=actor_id,
    )


def ensure_seating_for_order(db: Session, order: OpenOrder) -> None:
    """A guest tablet that already attached a customer gets a seating session too."""
    if order.table_id is None or order.customer_id is None or not _reservations_open(db):
        return
    if _active_session(db, order.table_id) is not None:
        sitting = _active_session(db, order.table_id)
        if sitting is not None:
            _link(db, sitting, order)
        return
    customer = db.get(Customer, order.customer_id)
    if customer is None:
        return
    sitting = TableSeatingSession(
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=customer.id,
        reservation_id=None,
        guest_count=order.covers or 1,
        assigned_employee_id=None,
        status="active",
        started_at=_now(),
    )
    db.add(sitting)
    db.flush()
    _link(db, sitting, order)
    _note(
        db,
        store_id=order.store_id,
        table_id=order.table_id,
        customer_id=customer.id,
        reservation_id=None,
        seating_session_id=sitting.id,
        order_id=order.id,
        event_type="customer_seated",
        description=f"{customer.name} seated at the table.",
        actor_id=order.opened_by_id,
    )
    db.commit()
