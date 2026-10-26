from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

Frequency = Literal["DAILY", "WEEKLY", "MONTHLY", "CUSTOM_DAYS"]
PlanStatus = Literal["ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"]
Fulfillment = Literal["DELIVERY", "COLLECTION"]
OccurrenceStatus = Literal["PENDING", "SNOOZED", "SKIPPED", "ORDERED", "DELIVERED"]


class PlanItemIn(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=10_000)
    unit: str = Field(default="PIECE", min_length=1, max_length=16)
    note: str | None = Field(default=None, max_length=160)


class PlanItemOut(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    quantity: int
    unit: str
    unit_factor: int
    base_quantity: int
    note: str | None
    available: int | None
    discontinued: bool


class PlanIn(ApiModel):
    customer_id: UUID
    name: str = Field(min_length=1, max_length=120)
    frequency: Frequency
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    month_day: int | None = Field(default=None, ge=1, le=28)
    start_on: date
    end_on: date | None = None
    preferred_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(default="Asia/Dubai", min_length=1, max_length=64)
    lead_days: int = Field(default=0, ge=0, le=14)
    fulfillment: Fulfillment = "DELIVERY"
    delivery_address: str | None = Field(default=None, max_length=255)
    notes: str = Field(default="", max_length=2000)
    salesperson_id: UUID | None = None
    store_id: UUID | None = None
    notify_customer: bool = False
    items: list[PlanItemIn] = Field(min_length=1, max_length=100)


class PlanUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    frequency: Frequency | None = None
    weekdays: list[int] | None = Field(default=None, max_length=7)
    month_day: int | None = Field(default=None, ge=1, le=28)
    start_on: date | None = None
    end_on: date | None = None
    clear_end: bool = False
    preferred_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    lead_days: int | None = Field(default=None, ge=0, le=14)
    fulfillment: Fulfillment | None = None
    delivery_address: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=2000)
    salesperson_id: UUID | None = None
    clear_salesperson: bool = False
    store_id: UUID | None = None
    notify_customer: bool | None = None
    items: list[PlanItemIn] | None = Field(default=None, min_length=1, max_length=100)


class PlanOut(ApiModel):
    id: UUID
    customer_id: UUID
    customer_name: str
    customer_code: str
    name: str
    frequency: Frequency
    weekdays: list[int]
    month_day: int | None
    start_on: date
    end_on: date | None
    next_on: date | None
    preferred_time: str | None
    timezone: str
    lead_days: int
    fulfillment: Fulfillment
    delivery_address: str | None
    notes: str
    status: PlanStatus
    salesperson_id: UUID | None
    salesperson_name: str | None
    store_id: UUID | None
    notify_customer: bool
    items: list[PlanItemOut]
    created_at: datetime
    updated_at: datetime


class OccurrenceOut(ApiModel):
    id: UUID
    plan_id: UUID
    plan_name: str
    customer_id: UUID
    customer_name: str
    customer_code: str
    customer_active: bool
    balance_cents: int
    scheduled_on: date
    preferred_time: str | None
    timezone: str
    status: OccurrenceStatus
    fulfillment: Fulfillment
    delivery_address: str | None
    salesperson_name: str | None
    store_id: UUID | None
    items: list[PlanItemOut]
    stock_note: str
    sales_order_id: UUID | None
    sales_order_number: str | None
    sales_order_status: str | None
    notification_status: str
    notification_error: str | None
    snooze_until: datetime | None
    skip_reason: str | None
    overdue: bool
    created_at: datetime
    completed_at: datetime | None


class SnoozeIn(ApiModel):
    hours: int | None = Field(default=None, ge=1, le=24 * 14)
    until: datetime | None = None


class SkipIn(ApiModel):
    reason: str = Field(min_length=3, max_length=160)


class LinkOrderIn(ApiModel):
    sales_order_id: UUID


class DraftOrderIn(ApiModel):
    user_id: UUID | None = None


class SummaryOut(ApiModel):
    due_today: int
    overdue: int
    pending: int
    ordered: int
    active_plans: int
    paused_plans: int
