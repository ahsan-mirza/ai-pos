from datetime import date, datetime
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

CODE_PATTERN = r"^[a-z0-9][a-z0-9-]{1,31}$"


class ChannelIn(ApiModel):
    name: str = Field(min_length=1, max_length=60)
    code: str = Field(pattern=CODE_PATTERN)
    store_id: UUID
    commission_bps: int = Field(default=0, ge=0, le=10_000)
    price_markup_bps: int = Field(default=0, ge=0, le=10_000)
    auto_accept: bool = False
    default_prep_minutes: int = Field(default=20, ge=1, le=240)
    is_active: bool = True


class ChannelOut(ChannelIn):
    id: UUID
    adapter: str
    # Where the provider posts orders (relative to the tenant's API address).
    webhook_path: str
    created_at: datetime


class ChannelSecretOut(ApiModel):
    """Shown once, when the channel is created or its secret rotated."""

    channel: ChannelOut
    webhook_secret: str


# --- The generic (normalised) webhook format ----------------------------------------------------------------


class ChannelCustomer(ApiModel):
    name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=40)

    @field_validator("phone")
    @classmethod
    def normalize_channel_phone(cls, value: str | None) -> str | None:
        from app.services.phone_numbers import normalize_phone

        return normalize_phone(value)
    address: str | None = Field(default=None, max_length=255)


class ChannelItemIn(ApiModel):
    # Matched to the catalogue by product id, SKU, barcode or scale PLU, in that order.
    product_id: UUID | None = None
    sku: str | None = Field(default=None, max_length=64)
    barcode: str | None = Field(default=None, max_length=64)
    plu: str | None = Field(default=None, max_length=6)
    name: str | None = Field(default=None, max_length=200)
    quantity: int = Field(ge=1, le=100)
    # Price on the app; when absent the till price plus the channel's markup is used.
    unit_price_cents: int | None = Field(default=None, ge=0)
    note: str | None = Field(default=None, max_length=160)


class ChannelOrderIn(ApiModel):
    external_id: str = Field(min_length=1, max_length=64)
    customer: ChannelCustomer | None = None
    items: list[ChannelItemIn] = Field(min_length=1, max_length=100)
    notes: str | None = Field(default=None, max_length=255)
    subtotal_cents: int | None = Field(default=None, ge=0)
    total_cents: int | None = Field(default=None, ge=0)
    # True when the customer paid the app (the usual case); false for cash on delivery.
    paid: bool = True
    prep_minutes: int | None = Field(default=None, ge=1, le=240)


class WebhookResult(ApiModel):
    order_id: UUID
    number: int
    # "created", or "duplicate" when this external id already arrived.
    result: str
    channel_status: str | None


class ManualChannelOrder(ApiModel):
    """A delivery-app order keyed in at the register: the items are added to the tab as usual."""

    channel_id: UUID
    external_ref: str = Field(min_length=1, max_length=64)
    customer_name: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=255)
    user_id: UUID | None = None


class ChannelDecision(ApiModel):
    revision: int
    user_id: UUID | None = None
    prep_minutes: int | None = Field(default=None, ge=1, le=240)
    reason: str | None = Field(default=None, max_length=160)


class PayoutIn(ApiModel):
    amount_cents: int = Field(ge=0)
    commission_cents: int = Field(default=0, ge=0)
    reference: str | None = Field(default=None, max_length=80)
    note: str | None = Field(default=None, max_length=255)
    received_at: datetime | None = None


class PayoutOut(PayoutIn):
    id: UUID
    channel_id: UUID
    channel_name: str
    received_at: datetime


class SettlementRow(ApiModel):
    channel_id: UUID
    name: str
    commission_bps: int
    orders: int
    # Paid by the app (channel tenders) in the period, the commission it should keep, and the rest it owes.
    gross_cents: int
    commission_cents: int
    net_cents: int
    paid_out_cents: int
    # Everything the channel still owes, all time: net of its orders less what it has paid out.
    outstanding_cents: int


class SettlementReport(ApiModel):
    start: date
    end: date
    rows: list[SettlementRow]
    payouts: list[PayoutOut]
