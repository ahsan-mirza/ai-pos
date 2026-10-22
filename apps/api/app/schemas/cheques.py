from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

ChequeStatus = Literal["RECEIVED", "DEPOSITED", "CLEARED", "BOUNCED", "CANCELLED"]
ChequeSource = Literal["SALE", "LEDGER"]


class ChequeAction(ApiModel):
    note: str = Field(default="", max_length=255)
    fee_cents: int = Field(default=0, ge=0, le=10_000_000)


class ChequeEventOut(ApiModel):
    from_status: str | None
    to_status: str
    user_name: str | None
    note: str
    occurred_at: datetime


class ChequeOut(ApiModel):
    id: UUID
    store_id: UUID
    customer_id: UUID | None
    customer_name: str | None
    cheque_number: str
    bank: str
    cheque_date: date
    amount_cents: int
    currency: str
    status: ChequeStatus
    source: ChequeSource
    sale_id: UUID | None
    sale_reference: str | None
    bounce_fee_cents: int
    received_by_name: str | None
    created_at: datetime
    events: list[ChequeEventOut]


class ChequeStats(ApiModel):
    in_hand_count: int
    in_hand_cents: int
    deposited_count: int
    deposited_cents: int
    due_this_week_count: int
    due_this_week_cents: int
    bounced_count: int
    bounced_cents: int
    exposure_cents: int


class ChequeList(ApiModel):
    stats: ChequeStats
    cheques: list[ChequeOut]
