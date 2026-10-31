from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

ReservationStatus = Literal[
    "pending", "confirmed", "arrived", "seated", "completed", "cancelled", "no_show", "rejected"
]
ReservationSource = Literal["pos", "portal", "waiter", "customer_app", "other"]
CancelReason = Literal[
    "customer_request", "time_change", "duplicate", "operational", "table_unavailable", "incorrect", "other"
]


class ReservationCustomerIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=254)


class ReservationCreate(ApiModel):
    store_id: UUID
    customer_id: UUID | None = None
    customer: ReservationCustomerIn | None = None
    table_id: UUID | None = None
    starts_at: datetime
    duration_minutes: int | None = Field(default=None, ge=15, le=360)
    expected_arrival_at: datetime | None = None
    guest_count: int = Field(ge=1, le=200)
    special_requests: str | None = Field(default=None, max_length=500)
    occasion: str | None = Field(default=None, max_length=80)
    internal_notes: str | None = Field(default=None, max_length=500)
    source: ReservationSource = "portal"
    assigned_employee_id: UUID | None = None
    override_reason: str | None = Field(default=None, max_length=160)


class ReservationUpdate(ApiModel):
    customer_id: UUID | None = None
    table_id: UUID | None = None
    starts_at: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=360)
    expected_arrival_at: datetime | None = None
    guest_count: int | None = Field(default=None, ge=1, le=200)
    special_requests: str | None = Field(default=None, max_length=500)
    occasion: str | None = Field(default=None, max_length=80)
    internal_notes: str | None = Field(default=None, max_length=500)
    assigned_employee_id: UUID | None = None
    reason: str | None = Field(default=None, max_length=160)
    override_reason: str | None = Field(default=None, max_length=160)


class CancelReservation(ApiModel):
    reason: CancelReason
    explanation: str | None = Field(default=None, max_length=500)
    notified: bool = False
    notes: str | None = Field(default=None, max_length=500)


class NoShowReservation(ApiModel):
    notes: str | None = Field(default=None, max_length=500)


class RejectReservation(ApiModel):
    reason: str = Field(min_length=3, max_length=160)


class WalkInCreate(ApiModel):
    store_id: UUID
    table_id: UUID
    customer_id: UUID | None = None
    customer: ReservationCustomerIn | None = None
    guest_count: int = Field(ge=1, le=200)
    assigned_employee_id: UUID | None = None


class ReleaseTable(ApiModel):
    reason: str | None = Field(default=None, max_length=160)


class ReservationSettingsIn(ApiModel):
    enabled: bool = True
    duration_minutes: int = Field(default=90, ge=15, le=360)
    buffer_minutes: int = Field(default=15, ge=0, le=120)
    grace_minutes: int = Field(default=15, ge=0, le=180)
    min_notice_minutes: int = Field(default=0, ge=0, le=10_080)
    max_advance_days: int = Field(default=30, ge=0, le=365)
    max_guests: int = Field(default=20, ge=1, le=200)
    allow_same_day: bool = True
    allow_walk_in: bool = True
    allow_guest_profiles: bool = False
    require_phone: bool = False
    confirm_on_create: bool = True
    notify_confirmation: bool = True
    notify_updates: bool = True
    notify_cancellation: bool = True
    notify_reminder: bool = False
    open_time: str = Field(default="09:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    close_time: str = Field(default="23:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Asia/Dubai", min_length=1, max_length=64)


class ReservationSettingsOut(ReservationSettingsIn):
    store_id: UUID


class CustomerPick(ApiModel):
    id: UUID
    code: str
    name: str
    phone: str | None
    email: str | None


class StatusEventOut(ApiModel):
    id: UUID
    previous_status: str | None
    status: str
    reason: str | None
    actor_user_id: UUID | None
    created_at: datetime


class ReservationOut(ApiModel):
    id: UUID
    reservation_number: str
    store_id: UUID
    customer_id: UUID
    customer_name: str
    customer_phone: str | None
    customer_email: str | None
    table_id: UUID | None
    table_label: str | None
    area_name: str | None
    guest_count: int
    status: ReservationStatus
    source: str
    occasion: str | None
    special_requests: str | None
    internal_notes: str | None
    assigned_employee_id: UUID | None
    starts_at: datetime
    ends_at: datetime
    expected_arrival_at: datetime | None
    confirmed_at: datetime | None
    arrived_at: datetime | None
    seated_at: datetime | None
    cancelled_at: datetime | None
    cancellation_reason: str | None
    customer_notified: bool
    notification_status: str
    notification_detail: str | None
    order_id: UUID | None = None
    events: list[StatusEventOut] = Field(default_factory=list)


class AvailabilityTable(ApiModel):
    table_id: UUID
    label: str
    area_name: str
    seats: int
    available: bool
    reason: str | None = None


class AvailabilityOut(ApiModel):
    starts_at: datetime
    ends_at: datetime
    tables: list[AvailabilityTable]


class ActivityEventOut(ApiModel):
    id: UUID
    store_id: UUID
    table_id: UUID
    customer_id: UUID | None
    reservation_id: UUID | None
    seating_session_id: UUID | None
    order_id: UUID | None
    event_type: str
    description: str
    actor_user_id: UUID | None
    created_at: datetime


class TableHistoryOut(ApiModel):
    table_id: UUID
    table_label: str
    starts_at: datetime
    ends_at: datetime
    events: list[ActivityEventOut]


class SeatResult(ApiModel):
    reservation_id: UUID | None
    seating_session_id: UUID
    order_id: UUID
    table_id: UUID
    table_label: str
    customer_id: UUID
    customer_name: str
    guest_count: int
