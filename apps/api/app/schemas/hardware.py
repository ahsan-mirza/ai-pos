from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

HardwareMode = Literal["lease", "purchase"]
PaymentStatus = Literal["awaiting_payment", "under_review", "paid", "canceled"]
FulfillmentStatus = Literal[
    "awaiting_payment",
    "under_review",
    "awaiting_fulfillment",
    "partial",
    "fulfilled",
    "canceled",
    "returned",
]
DepositDecision = Literal["held", "refund_approved", "refunded", "forfeited"]


class HardwareCategoryOut(ApiModel):
    id: UUID
    name: str
    sort_order: int
    active: bool


class HardwareCategoryIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    sort_order: int = Field(default=0, ge=0, le=100)
    active: bool = True
    reason: str = Field(min_length=3, max_length=500)


class HardwareItemOut(ApiModel):
    id: UUID
    sku: str
    name: str
    category_id: UUID
    category_name: str
    description: str
    image_url: str | None
    manufacturer: str
    model: str
    lease_available: bool
    purchase_available: bool
    monthly_fils: int
    deposit_fils: int
    fee_fils: int
    purchase_fils: int | None
    delivery_fils: int
    currency: str
    min_qty: int
    max_qty: int
    stock_qty: int | None
    counts_as_register: bool
    compatibility: str
    active: bool
    archived: bool
    available: bool
    internal_notes: str = ""


class HardwareItemIn(ApiModel):
    sku: str = Field(min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")
    name: str = Field(min_length=1, max_length=120)
    category_id: UUID
    description: str = Field(default="", max_length=1000)
    image_url: str | None = Field(default=None, max_length=300)
    manufacturer: str = Field(default="", max_length=80)
    model: str = Field(default="", max_length=80)
    lease_available: bool = True
    purchase_available: bool = False
    monthly_fils: int = Field(default=0, ge=0, le=100_000_000)
    deposit_fils: int = Field(default=0, ge=0, le=100_000_000)
    fee_fils: int = Field(default=0, ge=0, le=100_000_000)
    purchase_fils: int | None = Field(default=None, ge=0, le=100_000_000)
    delivery_fils: int = Field(default=0, ge=0, le=100_000_000)
    currency: str = Field(default="AED", min_length=3, max_length=3)
    min_qty: int = Field(default=1, ge=1, le=100)
    max_qty: int = Field(default=20, ge=1, le=100)
    stock_qty: int | None = Field(default=None, ge=0, le=100_000)
    counts_as_register: bool = False
    compatibility: str = Field(default="", max_length=500)
    active: bool = True
    archived: bool = False
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    internal_notes: str = Field(default="", max_length=1000)
    reason: str = Field(min_length=3, max_length=500)


class HardwarePick(ApiModel):
    item_id: UUID
    quantity: int = Field(ge=1, le=100)
    mode: HardwareMode = "lease"
    store_id: UUID | None = None
    store_label: str = Field(default="", max_length=80)


class HardwareLineOut(ApiModel):
    id: UUID
    item_id: UUID
    sku: str
    name: str
    store_id: UUID | None
    store_label: str
    mode: str
    quantity: int
    monthly_fils: int
    deposit_fils: int
    fee_fils: int
    purchase_fils: int
    delivery_fils: int
    fulfilled_qty: int
    serials: list[str]


class HardwareAssignmentOut(ApiModel):
    id: UUID
    order_line_id: UUID
    store_label: str
    serial: str
    quantity: int
    monthly_fils: int
    deposit_fils: int
    status: str
    deposit_decision: str
    delivered_at: datetime | None
    returned_at: datetime | None
    condition_note: str


class HardwareOrderOut(ApiModel):
    id: UUID
    reference: str
    tenant_id: UUID
    tenant_name: str
    invoice_id: UUID | None
    payment_status: str
    fulfillment_status: str
    monthly_fils: int
    deposit_fils: int
    one_time_fils: int
    currency: str
    line_count: int
    created_at: datetime
    lines: list[HardwareLineOut] = Field(default_factory=list)
    assignments: list[HardwareAssignmentOut] = Field(default_factory=list)


class FulfillmentIn(ApiModel):
    line_id: UUID
    fulfilled_qty: int = Field(ge=0, le=100)
    serials: list[str] = Field(default_factory=list, max_length=100)
    note: str = Field(default="", max_length=500)
    reason: str = Field(min_length=3, max_length=500)


class DepositDecisionIn(ApiModel):
    assignment_id: UUID
    decision: DepositDecision
    condition_note: str = Field(default="", max_length=500)
    reason: str = Field(min_length=3, max_length=500)
