"""Fashion rental requests and responses. Deposit amounts are never rental revenue."""

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import Field

from app.schemas.payloads import ApiModel

Offer = Literal["SALE", "RENT", "BOTH"]
RentalStatus = Literal["confirmed", "ready", "out", "inspection", "cleaning", "repair", "completed", "cancelled"]
PaymentKind = Literal["charge", "deposit", "deposit_refund", "deduction"]


class RentalPolicyIn(ApiModel):
    enabled: bool = True
    offer: Offer = "BOTH"
    price_per_day_cents: int = Field(ge=0)
    weekly_price_cents: int | None = Field(default=None, ge=0)
    deposit_cents: int = Field(default=0, ge=0)
    min_days: int = Field(default=1, ge=1, le=365)
    max_days: int | None = Field(default=None, ge=1, le=365)
    default_days: int = Field(default=1, ge=1, le=365)
    buffer_days: int = Field(default=0, ge=0, le=30)
    late_fee_per_day_cents: int = Field(default=0, ge=0)
    cleaning_fee_cents: int = Field(default=0, ge=0)
    requires_inspection: bool = True
    condition_note: str | None = Field(default=None, max_length=255)


class RentalPolicyOut(RentalPolicyIn):
    product_id: uuid.UUID
    product_name: str
    sku: str


class RentalQuote(ApiModel):
    product_id: uuid.UUID
    days: int
    quantity: int
    available: int
    rental_net_cents: int
    tax_cents: int
    deposit_cents: int
    total_due_cents: int
    currency: str


class RentalCreate(ApiModel):
    client_request_id: uuid.UUID
    customer_id: uuid.UUID
    store_id: uuid.UUID
    product_id: uuid.UUID
    start_date: date
    return_date: date
    quantity: int = Field(default=1, ge=1, le=100)
    serial_number_id: uuid.UUID | None = None
    discount_cents: int = Field(default=0, ge=0)
    pay_charge_cents: int = Field(default=0, ge=0)
    pay_deposit_cents: int = Field(default=0, ge=0)
    notes: str | None = Field(default=None, max_length=500)


class RentalPaymentIn(ApiModel):
    client_request_id: uuid.UUID
    kind: PaymentKind
    amount_cents: int = Field(gt=0)
    reason: str | None = Field(default=None, max_length=255)


class HandoverIn(ApiModel):
    condition: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=500)


class ReturnIn(ApiModel):
    condition: str = Field(min_length=1, max_length=255)
    notes: str | None = Field(default=None, max_length=500)
    damage_cents: int = Field(default=0, ge=0)
    cleaning: bool = False
    repair: bool = False
    waive_late: bool = False
    waive_reason: str | None = Field(default=None, max_length=255)


class ExtendIn(ApiModel):
    return_date: date


class RentalLineOut(ApiModel):
    product_id: uuid.UUID
    product_name: str
    sku: str
    quantity: int
    serial_number_id: uuid.UUID | None = None


class RentalOut(ApiModel):
    id: uuid.UUID
    reference: str
    store_id: uuid.UUID
    customer_id: uuid.UUID
    customer_name: str
    status: RentalStatus
    display_status: str
    start_date: date
    return_date: date
    currency: str
    agreed_net_cents: int
    discount_cents: int
    tax_cents: int
    extension_net_cents: int
    extension_tax_cents: int
    late_fee_cents: int
    cleaning_fee_cents: int
    damage_cents: int
    amount_paid_cents: int
    balance_cents: int
    deposit_due_cents: int
    deposit_collected_cents: int
    deposit_refunded_cents: int
    deposit_deducted_cents: int
    deposit_held_cents: int
    notes: str | None = None
    handover_at: datetime | None = None
    handover_condition: str | None = None
    returned_at: datetime | None = None
    return_condition: str | None = None
    return_notes: str | None = None
    lines: list[RentalLineOut]


class NamedCount(ApiModel):
    name: str
    count: int


class RentalSummary(ApiModel):
    currency: str
    pickups_today: int
    returns_today: int
    active: int
    overdue: int
    in_preparation: int
    rental_revenue_cents: int
    fee_cents: int
    deposits_held_cents: int
    outstanding_cents: int
    most_rented: list[NamedCount]


class AgreementOut(ApiModel):
    reference: str
    text: str


class CustomerPick(ApiModel):
    id: uuid.UUID
    name: str
    phone: str | None = None
