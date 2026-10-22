from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel, SerialKind

TradeInGrade = Literal["A", "B", "C", "D"]
TradeInPayout = Literal["CASH", "STORE_CREDIT", "SALE_CREDIT"]
TradeInStatus = Literal["ACCEPTED", "APPLIED", "CANCELLED"]


class TradeInCheck(ApiModel):
    kind: SerialKind
    value: str = Field(min_length=4, max_length=64)


class TradeInCheckOut(ApiModel):
    ok: bool
    message: str
    # Set when the unit was sold by this business before (a buyback).
    sold_here_at: datetime | None = None
    sold_as: str | None = None
    warranty_status: str | None = None


class TradeInChecklist(ApiModel):
    powers_on: bool
    screen_ok: bool
    body_ok: bool
    # iCloud / Google account and screen lock removed, so the unit can be reset and resold.
    account_removed: bool
    battery_pct: int | None = Field(default=None, ge=0, le=100)


class TradeInCreate(ApiModel):
    id: UUID
    store_id: UUID
    cashier_id: UUID
    product_id: UUID
    identifier_kind: SerialKind
    identifier_value: str = Field(min_length=4, max_length=64)
    grade: TradeInGrade
    checklist: TradeInChecklist
    notes: str = Field(default="", max_length=500)
    seller_name: str = Field(min_length=2, max_length=120)
    seller_phone: str = Field(min_length=5, max_length=40)
    seller_id_number: str = Field(min_length=5, max_length=40)
    customer_id: UUID | None = None
    offer_cents: int = Field(ge=0, le=100_000_000)
    resale_price_cents: int = Field(ge=0, le=100_000_000)
    payout: TradeInPayout


class TradeInOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    store_code: str
    product_id: UUID
    product_name: str
    resale_product_id: UUID
    resale_sku: str
    identifier_kind: SerialKind
    identifier_tail: str
    grade: TradeInGrade
    checklist: TradeInChecklist
    notes: str
    seller_name: str
    seller_phone: str
    seller_id_last4: str
    customer_id: UUID | None
    offer_cents: int
    resale_price_cents: int
    currency: str
    payout: TradeInPayout
    status: TradeInStatus
    sale_id: UUID | None
    store_credit_code: str | None
    cashier_name: str | None
    created_at: datetime


class TradeInList(ApiModel):
    items: list[TradeInOut]
    bought_cents: int
    count: int
    awaiting_sale_cents: int
