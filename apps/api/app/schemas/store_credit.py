from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel


class StoreCreditUseOut(ApiModel):
    sale_id: UUID
    invoice_number: str | None
    amount_cents: int
    used_at: datetime


class StoreCreditOut(ApiModel):
    id: UUID
    code: str
    store_id: UUID
    store_name: str
    currency: str
    initial_cents: int
    balance_cents: int
    issued_at: datetime
    return_id: UUID | None
    uses: list[StoreCreditUseOut]
    kind: Literal["VOUCHER", "GIFT_CARD"] = "VOUCHER"
    issued_sale_id: UUID | None = None
    customer_id: UUID | None = None
    customer_name: str | None = None
    expires_at: datetime | None = None
    voided_at: datetime | None = None
    note: str = ""
    # Spendable now: not voided, not expired, money left.
    usable: bool = True


class StoreCreditList(ApiModel):
    items: list[StoreCreditOut]
    outstanding_cents: int
    open_count: int


class GiftCardIssue(ApiModel):
    """Cards issued from the portal (promotions, goodwill, corporate orders) rather than sold at a till."""

    store_id: UUID
    amount_cents: int = Field(ge=100, le=100_000_000)
    count: int = Field(default=1, ge=1, le=200)
    customer_id: UUID | None = None
    note: str = Field(min_length=3, max_length=255)


class GiftCardVoid(ApiModel):
    note: str = Field(min_length=3, max_length=255)


class GiftCardProductOut(ApiModel):
    """The service product a register adds to sell a gift card, and the business's gift-card rules."""

    product_id: UUID
    sku: str
    name: str
    min_cents: int
    max_cents: int
    expiry_months: int | None
