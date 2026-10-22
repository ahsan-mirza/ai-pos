from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from app.schemas.payloads import ApiModel

ShiftStatus = Literal["OPEN", "CLOSED"]
CashMovementKind = Literal["PAY_IN", "PAY_OUT", "CASH_DROP", "NO_SALE"]
MAX_CASH_CENTS = 100_000_000


class RegisterShiftPayload(ApiModel):
    id: UUID
    store_id: UUID
    opened_by_id: UUID
    opened_at: datetime
    opening_float_cents: int = Field(ge=0, le=MAX_CASH_CENTS)
    currency: str = Field(min_length=3, max_length=3)
    status: ShiftStatus = "OPEN"
    closed_by_id: UUID | None = None
    closed_at: datetime | None = None
    counted_cash_cents: int | None = Field(default=None, ge=0, le=MAX_CASH_CENTS)
    z_number: str | None = Field(default=None, max_length=40)
    blind_close: bool = True
    notes: str = Field(default="", max_length=500)
    counted_foreign: dict[str, int] = Field(default_factory=dict)

    @field_validator("currency")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def closing_fields(self) -> Self:
        if self.status == "CLOSED" and (
            self.closed_by_id is None or self.closed_at is None or self.counted_cash_cents is None
        ):
            raise ValueError("Closing a shift needs who closed it, when, and the counted cash.")
        return self


class CashMovementPayload(ApiModel):
    id: UUID
    shift_id: UUID
    store_id: UUID
    user_id: UUID
    kind: CashMovementKind
    amount_cents: int = Field(ge=0, le=MAX_CASH_CENTS)
    currency: str = Field(min_length=3, max_length=3)
    reason: str = Field(default="", max_length=250)
    occurred_at: datetime

    @field_validator("currency")
    @classmethod
    def upper(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def amount_matches_kind(self) -> Self:
        if self.kind == "NO_SALE" and self.amount_cents != 0:
            raise ValueError("A no-sale drawer open moves no cash.")
        if self.kind != "NO_SALE" and self.amount_cents == 0:
            raise ValueError("Enter the amount of cash moved.")
        if self.kind != "NO_SALE" and len(self.reason.strip()) < 3:
            raise ValueError("Give a reason for the cash movement.")
        return self


class ServerTips(ApiModel):
    user_id: UUID | None
    name: str
    sales_count: int
    tips_cents: int


class TipReport(ApiModel):
    """The tip pool for a period: what each member of staff earned in tips, and the service charge taken."""

    start: date
    end: date
    store_id: UUID | None
    sales_count: int
    tips_cents: int
    service_charge_cents: int
    by_server: list[ServerTips]


class ShiftReport(ApiModel):
    sales_count: int
    sales_total_cents: int
    tax_cents: int
    tenders: dict[str, int]
    on_account_cents: int
    returns_count: int
    refunds_total_cents: int
    refund_tenders: dict[str, int]
    pay_in_cents: int
    pay_out_cents: int
    drops_cents: int
    no_sale_count: int
    opening_float_cents: int
    expected_cash_cents: int
    # Foreign cash expected per currency (in that currency's minor units), and what was counted at close.
    foreign_cash: dict[str, int] = Field(default_factory=dict)
    foreign_counted: dict[str, int] = Field(default_factory=dict)
    # Restaurant: tips are owed to staff (not revenue); the service charge is revenue.
    tips_cents: int = 0
    service_charge_cents: int = 0
    tips_by_server: list[ServerTips] = Field(default_factory=list)
    # Card and pay-later takings confirmed by each provider ("CARD:ngenius", "BNPL:tabby"), for the Z report.
    provider_totals: dict[str, int] = Field(default_factory=dict)
    # Cash repair deposits taken on this shift, and cash deposits handed back on this shift.
    deposit_cents: int = 0
    deposit_refund_cents: int = 0


class CashMovementOut(ApiModel):
    id: UUID
    kind: CashMovementKind
    amount_cents: int
    reason: str
    user_name: str
    occurred_at: datetime


class ShiftOut(ApiModel):
    id: UUID
    store_id: UUID
    store_code: str
    device_code: str | None
    opened_by_name: str
    closed_by_name: str | None
    opened_at: datetime
    closed_at: datetime | None
    currency: str
    status: ShiftStatus
    opening_float_cents: int
    counted_cash_cents: int | None
    expected_cash_cents: int
    variance_cents: int | None
    blind_close: bool
    z_number: str | None
    report: ShiftReport
    movements: list[CashMovementOut]
