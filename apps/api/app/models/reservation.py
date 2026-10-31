"""Restaurant and cafe reservations, the seating session behind a table, and append-only table history.

The live check stays on OpenOrder. These rows remember who booked the table, who sat down, and what
happened, including after the order is paid and the table is used again.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, utcnow

RESERVATION_STATUSES = (
    "pending",
    "confirmed",
    "arrived",
    "seated",
    "completed",
    "cancelled",
    "no_show",
    "rejected",
)
RESERVATION_SOURCES = ("pos", "portal", "waiter", "customer_app", "other")
SEATING_STATUSES = ("active", "closed")
CANCEL_REASONS = (
    "customer_request",
    "time_change",
    "duplicate",
    "operational",
    "table_unavailable",
    "incorrect",
    "other",
)


class ReservationSettings(TenantScoped, TimestampMixin, Base):
    """Booking rules for one branch. Missing row means the defaults in reservation_service."""

    __tablename__ = "reservation_settings"
    __table_args__ = (
        Index("uq_reservation_settings_store", "tenant_id", "store_id", unique=True),
        CheckConstraint("duration_minutes >= 15", name="ck_reservation_settings_duration"),
        CheckConstraint("buffer_minutes >= 0", name="ck_reservation_settings_buffer"),
        CheckConstraint("grace_minutes >= 0", name="ck_reservation_settings_grace"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=90)
    buffer_minutes: Mapped[int] = mapped_column(Integer, default=15)
    grace_minutes: Mapped[int] = mapped_column(Integer, default=15)
    min_notice_minutes: Mapped[int] = mapped_column(Integer, default=0)
    max_advance_days: Mapped[int] = mapped_column(Integer, default=30)
    max_guests: Mapped[int] = mapped_column(Integer, default=20)
    allow_same_day: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_walk_in: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_guest_profiles: Mapped[bool] = mapped_column(Boolean, default=False)
    require_phone: Mapped[bool] = mapped_column(Boolean, default=False)
    confirm_on_create: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_confirmation: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_updates: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_cancellation: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_reminder: Mapped[bool] = mapped_column(Boolean, default=False)
    open_time: Mapped[str] = mapped_column(String(5), default="09:00")
    close_time: Mapped[str] = mapped_column(String(5), default="23:00")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Dubai")


class Reservation(TenantScoped, TimestampMixin, Base):
    __tablename__ = "reservations"
    __table_args__ = (
        Index("uq_reservations_number", "tenant_id", "store_id", "reservation_number", unique=True),
        Index("ix_reservations_table_window", "table_id", "status", "starts_at"),
        Index("ix_reservations_store_start", "store_id", "starts_at"),
        CheckConstraint("guest_count >= 1", name="ck_reservations_guests"),
        CheckConstraint(
            "status IN ('pending','confirmed','arrived','seated','completed','cancelled','no_show','rejected')",
            name="ck_reservations_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    table_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("dining_tables.id"), nullable=True
    )
    reservation_number: Mapped[str] = mapped_column(String(16))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # ends_at plus the cleaning buffer. Overlap checks use this so two bookings cannot share the turn.
    blocked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expected_arrival_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    guest_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    source: Mapped[str] = mapped_column(String(16), default="portal")
    occasion: Mapped[str | None] = mapped_column(String(80), nullable=True)
    special_requests: Mapped[str | None] = mapped_column(String(500), nullable=True)
    internal_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assigned_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    seated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cancellation_detail: Mapped[str | None] = mapped_column(String(500), nullable=True)
    customer_notified: Mapped[bool] = mapped_column(Boolean, default=False)
    notification_status: Mapped[str] = mapped_column(String(16), default="pending")
    notification_detail: Mapped[str | None] = mapped_column(String(300), nullable=True)
    notification_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outbound_messages.id"), nullable=True
    )


class ReservationStatusEvent(TenantScoped, Base):
    """One row per status change. Rows are insert-only."""

    __tablename__ = "reservation_status_events"
    __table_args__ = (Index("ix_reservation_status_events_reservation", "reservation_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    reservation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reservations.id"))
    previous_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TableSeatingSession(TenantScoped, TimestampMixin, Base):
    """Who is sitting at a table. Walk-ins leave reservation_id empty. History stays after the session closes."""

    __tablename__ = "table_seating_sessions"
    __table_args__ = (
        Index("ix_seating_sessions_table", "table_id", "status"),
        CheckConstraint("guest_count >= 1", name="ck_seating_sessions_guests"),
        CheckConstraint("status IN ('active', 'closed')", name="ck_seating_sessions_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dining_tables.id"))
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"))
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id"), nullable=True
    )
    guest_count: Mapped[int] = mapped_column(Integer)
    assigned_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SeatingSessionOrder(TenantScoped, Base):
    """Orders taken during one seating. A later sitting of the same table gets a new session, not a rewritten link."""

    __tablename__ = "seating_session_orders"
    __table_args__ = (Index("uq_seating_session_orders_order", "order_id", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    seating_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_seating_sessions.id"), index=True
    )
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("open_orders.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TableActivityEvent(TenantScoped, Base):
    """Append-only activity for a table. The 24-hour screen is a filter, not a retention policy."""

    __tablename__ = "table_activity_events"
    __table_args__ = (
        Index("ix_table_activity_table_created", "table_id", "created_at"),
        Index("ix_table_activity_store_created", "store_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    table_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("dining_tables.id"))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    reservation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reservations.id"), nullable=True
    )
    seating_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("table_seating_sessions.id"), nullable=True
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("open_orders.id"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    description: Mapped[str] = mapped_column(String(300))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    event_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


def _refuse_history_change(_mapper: object, _connection: object, _target: object) -> None:
    raise RuntimeError("Table and reservation history cannot be changed or deleted.")


for _history in (TableActivityEvent, ReservationStatusEvent):
    event.listen(_history, "before_update", _refuse_history_change)
    event.listen(_history, "before_delete", _refuse_history_change)
