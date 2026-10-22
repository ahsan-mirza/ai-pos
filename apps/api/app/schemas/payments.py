from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

IntentStatus = Literal["PENDING", "AUTHORIZED", "PAID", "DECLINED", "EXPIRED", "CANCELLED"]
Phone = Field(pattern=r"^\+?[0-9 ]{7,20}$")


class IntentCreate(ApiModel):
    amount_cents: int = Field(ge=1, le=100_000_000)
    store_id: UUID | None = None
    reference: str | None = Field(default=None, pattern=r"^[A-Za-z0-9-]{4,25}$")


class CardIntentCreate(ApiModel):
    amount_cents: int = Field(ge=1, le=100_000_000)
    store_id: UUID | None = None
    # The till's own terminal; omitted, the store's first active terminal takes it.
    terminal_id: UUID | None = None


class BnplItem(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=10_000)
    unit_cents: int = Field(ge=0, le=100_000_000)
    sku: str = Field(default="", max_length=64)


class BnplIntentCreate(ApiModel):
    amount_cents: int = Field(ge=1, le=100_000_000)
    store_id: UUID | None = None
    provider: str = Field(pattern="^(simulator|tabby|tamara)$")
    customer_phone: str = Phone
    customer_name: str = Field(default="", max_length=120)
    customer_email: str = Field(default="", max_length=160)
    items: list[BnplItem] = Field(default_factory=list, max_length=200)


class SimulateOutcome(ApiModel):
    outcome: Literal["approve", "decline"]


class IntentOut(ApiModel):
    id: UUID
    channel: Literal["QR", "CARD", "BNPL"] = "QR"
    provider: str
    amount_cents: int
    currency: str
    reference: str
    qr_payload: str
    status: IntentStatus
    expires_at: datetime
    paid_at: datetime | None
    sale_id: UUID | None
    customer_url: str | None = None
    auth_code: str | None = None
    card_brand: str | None = None
    card_last4: str | None = None
    failure_reason: str | None = None
    refunded_cents: int = 0
    terminal_id: UUID | None = None
    simulated: bool = False


class PaymentRow(IntentOut):
    store_id: UUID
    store_name: str
    created_at: datetime
    sale_number: str | None = None


class PaymentList(ApiModel):
    items: list[PaymentRow]
    total: int
    paid_cents: int
    refunded_cents: int


class RefundOut(ApiModel):
    id: UUID
    intent_id: UUID
    return_id: UUID | None
    provider: str
    channel: str
    amount_cents: int
    status: Literal["PENDING", "SUCCEEDED", "FAILED"]
    provider_ref: str | None
    error: str | None
    attempts: int
    created_at: datetime


class TerminalIn(ApiModel):
    store_id: UUID
    provider: str = Field(pattern="^(simulator|ngenius|geidea)$")
    terminal_ref: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._:-]+$")
    label: str = Field(min_length=1, max_length=80)
    device_id: UUID | None = None
    is_active: bool = True


class TerminalPatch(ApiModel):
    label: str | None = Field(default=None, min_length=1, max_length=80)
    device_id: UUID | None = None
    clear_device: bool = False
    is_active: bool | None = None


class TerminalOut(ApiModel):
    id: UUID
    store_id: UUID
    provider: str
    terminal_ref: str
    label: str
    device_id: UUID | None
    is_active: bool
    last_checked_at: datetime | None
    last_check_ok: bool | None


class TerminalCheck(ApiModel):
    ok: bool
    message: str


class ProviderOut(ApiModel):
    name: str
    label: str
    channel: Literal["CARD", "BNPL"]
    configured: bool
    simulated: bool
    missing: list[str]


class PaymentsConfig(ApiModel):
    """What a till needs: whether card amounts go to a terminal, which terminal, and the BNPL choices."""

    card_provider: ProviderOut
    bnpl: list[ProviderOut]
    terminals: list[TerminalOut]
    # True when the store has an active terminal: a card tender then needs a terminal approval or a manager.
    card_terminal_required: bool
    default_terminal_id: UUID | None
    # Approve/decline buttons for simulated providers (never in live production).
    simulator_controls: bool
