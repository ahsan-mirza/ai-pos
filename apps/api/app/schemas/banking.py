from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.payloads import ApiModel

LineStatus = Literal["UNMATCHED", "MATCHED", "IGNORED"]
BookKind = Literal[
    "CARD_SETTLEMENT",
    "QR_SETTLEMENT",
    "BNPL_SETTLEMENT",
    "TRANSFER_RECEIPT",
    "ACCOUNT_RECEIPT",
    "CHEQUE_DEPOSIT",
    "SUPPLIER_PAYMENT",
    "EXPENSE",
    "PETTY_CASH_TOPUP",
    "PAYROLL",
]


class BankAccountWrite(ApiModel):
    name: str = Field(min_length=2, max_length=80)
    bank: str = Field(min_length=2, max_length=80)
    iban: str | None = Field(default=None, max_length=34)
    is_active: bool = True

    @field_validator("iban")
    @classmethod
    def _iban(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.replace(" ", "").upper()
        if cleaned and (len(cleaned) < 15 or not cleaned[:2].isalpha() or not cleaned.isalnum()):
            raise ValueError("Enter a valid IBAN, e.g. AE070331234567890123456.")
        return cleaned or None


class BankAccountOut(ApiModel):
    id: UUID
    name: str
    bank: str
    iban: str | None
    currency: str
    is_active: bool
    unmatched_count: int
    statement_balance_cents: int | None
    last_statement_on: date | None


class StatementOut(ApiModel):
    id: UUID
    file_name: str
    file_format: Literal["CSV", "MT940"]
    period_from: date | None
    period_to: date | None
    lines_imported: int
    lines_skipped: int
    imported_at: datetime
    imported_by_name: str | None


class StatementImportOut(ApiModel):
    statement: StatementOut
    auto_matched: int


class StatementLineOut(ApiModel):
    id: UUID
    booked_on: date
    description: str
    reference: str
    amount_cents: int
    balance_cents: int | None
    status: LineStatus
    matched_key: str | None
    matched_label: str
    fee_cents: int
    auto_matched: bool
    match_note: str


class BookItemOut(ApiModel):
    key: str
    kind: BookKind
    booked_on: date
    amount_cents: int
    label: str
    reference: str
    store_code: str | None


class CandidateOut(BookItemOut):
    score: int
    fee_cents: int


class MatchWrite(ApiModel):
    key: str = Field(min_length=3, max_length=120)
    note: str = Field(default="", max_length=255)


class BookChargeWrite(ApiModel):
    store_id: UUID | None = None


class IgnoreWrite(ApiModel):
    note: str = Field(min_length=2, max_length=255)


class AutoMatchOut(ApiModel):
    matched: int


class ReconciliationSummary(ApiModel):
    account_id: UUID
    lines: int
    matched: int
    unmatched: int
    ignored: int
    unmatched_in_cents: int
    unmatched_out_cents: int
    fees_cents: int
    statement_balance_cents: int | None
    period_from: date | None
    period_to: date | None
    outstanding: list[BookItemOut]
