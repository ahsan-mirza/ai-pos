from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel, ComboChoice, ModifierChoice

ServiceType = Literal["DINE_IN", "TAKEAWAY", "DELIVERY"]
OrderStatus = Literal["OPEN", "SETTLED", "VOID"]
TableStatus = Literal["free", "seated", "ordered", "bill"]


class OrderItemIn(ApiModel):
    # Registers mint line ids so retries and offline copies never duplicate a line.
    id: UUID
    product_id: UUID
    quantity: int = Field(ge=1, le=1000)
    unit_price_cents: int = Field(ge=0)
    modifiers: list[ModifierChoice] = Field(default_factory=list, max_length=30)
    # Meal components for a combo item; each fires to its own kitchen station.
    components: list[ComboChoice] = Field(default_factory=list, max_length=20)
    seat: int | None = Field(default=None, ge=1, le=99)
    note: str | None = Field(default=None, max_length=160)


class OrderCreate(ApiModel):
    id: UUID
    store_id: UUID
    service_type: ServiceType = "DINE_IN"
    table_id: UUID | None = None
    covers: int = Field(default=0, ge=0, le=200)
    name: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=255)
    customer_id: UUID | None = None
    # The cashier working the order; registers authenticate as the device.
    user_id: UUID | None = None
    items: list[OrderItemIn] = Field(default_factory=list, max_length=200)


class OrderUpdate(ApiModel):
    revision: int
    user_id: UUID | None = None
    covers: int | None = Field(default=None, ge=0, le=200)
    name: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=255)
    customer_id: UUID | None = None
    service_type: ServiceType | None = None


class OrderItemsAdd(ApiModel):
    revision: int
    user_id: UUID | None = None
    items: list[OrderItemIn] = Field(min_length=1, max_length=100)


class OrderAction(ApiModel):
    revision: int
    user_id: UUID | None = None


class ItemVoid(ApiModel):
    revision: int
    user_id: UUID | None = None
    reason: str = Field(min_length=3, max_length=160)
    # Required once the item has gone to the kitchen: a user holding pos:void_sent_item.
    approved_by_id: UUID | None = None


class OrderMove(ApiModel):
    revision: int
    user_id: UUID | None = None
    table_id: UUID | None


class OrderMerge(ApiModel):
    revision: int
    user_id: UUID | None = None
    # The order this one is folded into; this order is voided once its lines move.
    into_order_id: UUID
    into_revision: int


class OrderItemOut(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    unit_price_cents: int
    modifiers: list[dict] = Field(default_factory=list)
    components: list[dict] = Field(default_factory=list)
    seat: int | None
    note: str | None
    sent_at: datetime | None
    voided_at: datetime | None
    void_reason: str | None
    paid_sale_id: UUID | None
    # Kitchen progress once the KDS module is on: "new", "preparing", "ready", "bumped".
    kitchen_status: str | None = None


class OrderOut(ApiModel):
    id: UUID
    store_id: UUID
    number: int
    service_type: ServiceType
    status: OrderStatus
    table_id: UUID | None
    table_label: str | None
    covers: int
    name: str | None
    note: str | None
    customer_id: UUID | None
    opened_by_id: UUID
    opened_by_name: str | None
    revision: int
    bill_requested_at: datetime | None
    opened_at: datetime
    closed_at: datetime | None
    updated_at: datetime
    channel_id: UUID | None = None
    channel_name: str | None = None
    external_ref: str | None = None
    channel_status: str | None = None
    prep_minutes: int | None = None
    items: list[OrderItemOut]
    # Unpaid, unvoided lines at their ordered prices (before tax and service charge).
    open_cents: int


class OrderSyncItem(OrderItemIn):
    sent_at: datetime | None = None
    voided_at: datetime | None = None
    void_reason: str | None = Field(default=None, max_length=160)


class OrderSyncPayload(ApiModel):
    """An order a register opened (or added to) while offline. Lines merge by id; existing lines are never
    overwritten, so an offline copy cannot undo what other registers did online."""

    id: UUID
    store_id: UUID
    service_type: ServiceType = "DINE_IN"
    table_id: UUID | None = None
    covers: int = Field(default=0, ge=0, le=200)
    name: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=255)
    opened_by_id: UUID
    opened_at: datetime
    items: list[OrderSyncItem] = Field(default_factory=list, max_length=200)


class DiningAreaIn(ApiModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=60)
    position: int = Field(default=0, ge=0, le=1000)
    is_active: bool = True


class DiningTableIn(ApiModel):
    area_id: UUID
    label: str = Field(min_length=1, max_length=16)
    seats: int = Field(default=4, ge=1, le=50)
    shape: Literal["square", "round", "rect"] = "square"
    x: int = Field(default=0, ge=0, le=200)
    y: int = Field(default=0, ge=0, le=200)
    w: int = Field(default=2, ge=1, le=20)
    h: int = Field(default=2, ge=1, le=20)
    is_active: bool = True


class DiningTableOut(DiningTableIn):
    id: UUID
    # Live state from the open orders seated at it.
    status: TableStatus = "free"
    order_id: UUID | None = None
    order_number: int | None = None
    covers: int = 0
    seated_at: datetime | None = None
    open_cents: int = 0


class DiningAreaOut(DiningAreaIn):
    id: UUID
    tables: list[DiningTableOut]


class FloorOut(ApiModel):
    store_id: UUID
    areas: list[DiningAreaOut]
