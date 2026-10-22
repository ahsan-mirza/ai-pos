from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel, PaymentMethod, SaleTenderPayload

OrderStatus = Literal["DRAFT", "CONFIRMED", "PICKING", "PARTIALLY_DELIVERED", "DELIVERED", "CLOSED", "CANCELLED"]
OrderSource = Literal["manual", "register", "quote", "b2b", "ecommerce", "rep"]


class SalesOrderLineIn(ApiModel):
    product_id: UUID
    quantity: int = Field(ge=1, le=100_000)
    # Omitted: the customer's tier / volume price. A lower price needs `price_approved_by_id` on the order.
    unit_price_cents: int | None = Field(default=None, ge=0)
    description: str | None = Field(default=None, max_length=160)


class SalesOrderCreate(ApiModel):
    id: UUID | None = None
    store_id: UUID
    customer_id: UUID
    sale_type: Literal["WHOLESALE", "RETAIL"] = "WHOLESALE"
    lines: list[SalesOrderLineIn] = Field(min_length=1, max_length=300)
    requested_date: date | None = None
    delivery_address: str | None = Field(default=None, max_length=255)
    customer_reference: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    # Confirm straight away (reserve stock and check credit).
    confirm: bool = False
    # A manager who agreed prices below the list price, and who may let the order exceed the credit limit.
    price_approved_by_id: UUID | None = None
    credit_approved_by_id: UUID | None = None
    # Registers call as the device on behalf of the signed-in cashier.
    user_id: UUID | None = None
    source: OrderSource = "manual"
    channel_ref: str | None = Field(default=None, max_length=64)


class SalesOrderUpdate(ApiModel):
    lines: list[SalesOrderLineIn] | None = Field(default=None, min_length=1, max_length=300)
    requested_date: date | None = None
    delivery_address: str | None = Field(default=None, max_length=255)
    customer_reference: str | None = Field(default=None, max_length=64)
    notes: str | None = Field(default=None, max_length=2000)
    price_approved_by_id: UUID | None = None


class ConfirmIn(ApiModel):
    credit_approved_by_id: UUID | None = None


class DispatchLineIn(ApiModel):
    order_line_id: UUID
    quantity: int = Field(ge=1, le=100_000)
    # IMEIs / serials for serialized lines; omitted, free units at the branch are assigned.
    serials: list[str] = Field(default_factory=list, max_length=1000)


class DispatchIn(ApiModel):
    lines: list[DispatchLineIn] = Field(min_length=1, max_length=300)
    driver_id: UUID | None = None
    vehicle: str | None = Field(default=None, max_length=40)
    # Retail customers pay as the goods leave; wholesale customers are invoiced on account by default.
    payment_method: PaymentMethod | None = None
    tenders: list[SaleTenderPayload] | None = Field(default=None, max_length=12)
    credit_approved_by_id: UUID | None = None


class DeliverIn(ApiModel):
    receiver_name: str = Field(min_length=1, max_length=120)
    # PNG data URL drawn on the driver's phone.
    signature: str | None = Field(default=None, max_length=400_000, pattern=r"^data:image/png;base64,")
    note: str | None = Field(default=None, max_length=255)


class CancelLineIn(ApiModel):
    order_line_id: UUID
    quantity: int = Field(ge=1, le=100_000)


class CancelLinesIn(ApiModel):
    lines: list[CancelLineIn] = Field(min_length=1, max_length=300)
    reason: str = Field(min_length=3, max_length=255)


class ReasonIn(ApiModel):
    reason: str = Field(min_length=3, max_length=255)


class SalesOrderLineOut(ApiModel):
    id: UUID
    product_id: UUID
    product_name: str
    sku: str
    is_serialized: bool
    description: str | None
    quantity_ordered: int
    quantity_reserved: int
    quantity_delivered: int
    quantity_cancelled: int
    outstanding: int
    # Not yet reserved: waiting for stock.
    backordered: int
    unit_price_cents: int
    list_price_cents: int
    tax_cents: int
    line_total_cents: int
    bin_location: str | None = None
    available_now: int = 0


class PickListOut(ApiModel):
    id: UUID
    number: str
    status: str
    created_at: datetime
    lines: list[dict]


class DeliveryNoteLineOut(ApiModel):
    order_line_id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    serial_suffixes: list[str] = Field(default_factory=list)


class DeliveryNoteOut(ApiModel):
    id: UUID
    number: str
    order_id: UUID
    order_number: str
    customer_name: str
    delivery_address: str | None
    status: str
    sale_id: UUID | None
    invoice_number: str | None
    invoice_total_cents: int | None
    driver_name: str | None
    vehicle: str | None
    dispatched_at: datetime
    delivered_at: datetime | None
    receiver_name: str | None
    has_signature: bool
    pod_note: str | None
    lines: list[DeliveryNoteLineOut]


class SalesOrderOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    customer_id: UUID
    customer_name: str
    customer_type: str
    status: OrderStatus
    sale_type: str
    price_tier: str
    currency: str
    source: str
    quote_id: UUID | None
    channel_ref: str | None
    customer_reference: str | None
    requested_date: date | None
    delivery_address: str | None
    notes: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    delivered_cents: int
    created_at: datetime
    confirmed_at: datetime | None
    closed_at: datetime | None
    lines: list[SalesOrderLineOut]
    pick_lists: list[PickListOut] = Field(default_factory=list)
    deliveries: list[DeliveryNoteOut] = Field(default_factory=list)


class SalesOrderRow(ApiModel):
    id: UUID
    number: str
    customer_name: str
    status: OrderStatus
    source: str
    total_cents: int
    currency: str
    lines: int
    outstanding_units: int
    backordered_units: int
    requested_date: date | None
    created_at: datetime


class BackorderRow(ApiModel):
    order_id: UUID
    order_number: str
    customer_name: str
    product_id: UUID
    product_name: str
    sku: str
    backordered: int
    available_now: int
    requested_date: date | None
    ordered_at: datetime
