from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from app.schemas.payloads import ApiModel

AccountType = Literal["ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE"]


class GlAccountWrite(ApiModel):
    code: str = Field(min_length=1, max_length=16, pattern=r"^[A-Za-z0-9.\-]+$")
    name: str = Field(min_length=2, max_length=120)
    type: AccountType
    is_active: bool = True


class GlAccountRow(ApiModel):
    id: UUID
    code: str
    name: str
    type: AccountType
    is_system: bool
    is_active: bool
    balance_cents: int


class AccountingSettings(ApiModel):
    fiscal_year_start_month: int = Field(default=1, ge=1, le=12)
    locked_until: date | None = None
    inventory_costing: str = "FIFO"


class CostingMethodWrite(ApiModel):
    method: Literal["FIFO", "WEIGHTED_AVERAGE"]
    reason: str = Field(min_length=3, max_length=500)
    # Required once a sale has a posted cost. Posted costs are not rewritten.
    convert: bool = False


class LockWrite(ApiModel):
    locked_until: date | None


class PostRequest(ApiModel):
    start: date = Field(alias="from")
    end: date = Field(alias="to")


class PostResult(ApiModel):
    posted: int
    reversed: int
    unchanged: int
    unbalanced: list[str]


class JournalLineIn(ApiModel):
    account_id: UUID
    debit_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    credit_cents: int = Field(default=0, ge=0, le=100_000_000_000)
    memo: str = Field(default="", max_length=255)


class ManualJournalCreate(ApiModel):
    entry_date: date
    reference: str = Field(default="", max_length=80)
    memo: str = Field(min_length=3, max_length=255)
    lines: list[JournalLineIn] = Field(min_length=2, max_length=100)


class ReverseRequest(ApiModel):
    entry_date: date | None = None
    memo: str = Field(default="", max_length=255)


class JournalLineOut(ApiModel):
    account_id: UUID
    account_code: str
    account_name: str
    debit_cents: int
    credit_cents: int
    memo: str


class JournalEntryOut(ApiModel):
    id: UUID
    number: int
    entry_date: date
    original_date: date | None
    journal: str
    reference: str
    memo: str
    source_ref: str | None
    is_active: bool
    reversal_of_id: UUID | None
    reversible: bool
    total_cents: int
    created_by_name: str | None
    created_at: datetime
    lines: list[JournalLineOut]


class TrialBalanceRow(ApiModel):
    account_id: UUID
    code: str
    name: str
    type: AccountType
    opening_cents: int
    debit_cents: int
    credit_cents: int
    closing_cents: int


class TrialBalance(ApiModel):
    period_from: date
    period_to: date
    currency: str
    rows: list[TrialBalanceRow]
    total_debit_cents: int
    total_credit_cents: int


class StatementRow(ApiModel):
    account_id: UUID | None
    code: str
    name: str
    amount_cents: int


class StatementSection(ApiModel):
    key: str
    title: str
    rows: list[StatementRow]
    total_cents: int


class SubledgerCheck(ApiModel):
    key: Literal["inventory", "receivables", "payables"]
    label: str
    books_cents: int
    subledger_cents: int
    difference_cents: int


class BalanceSheet(ApiModel):
    as_of: date
    currency: str
    sections: list[StatementSection]
    total_assets_cents: int
    total_liabilities_cents: int
    total_equity_cents: int
    balanced: bool
    checks: list[SubledgerCheck]


class IncomeStatement(ApiModel):
    period_from: date
    period_to: date
    currency: str
    sections: list[StatementSection]
    gross_profit_cents: int
    operating_profit_cents: int
    net_profit_cents: int


class LedgerRow(ApiModel):
    entry_id: UUID
    number: int
    entry_date: date
    journal: str
    reference: str
    memo: str
    debit_cents: int
    credit_cents: int
    balance_cents: int


class AccountLedger(ApiModel):
    account: GlAccountRow
    period_from: date
    period_to: date
    opening_cents: int
    closing_cents: int
    rows: list[LedgerRow]
    truncated: bool


class CloseYearRequest(ApiModel):
    year_end: date


class CorporateTaxEstimate(ApiModel):
    fiscal_year: int
    period_from: date
    period_to: date
    currency: str
    revenue_cents: int
    profit_before_tax_cents: int
    add_backs_cents: int
    deductions_cents: int
    taxable_income_cents: int
    threshold_cents: int
    rate_bps: int
    tax_cents: int
    small_business_relief_eligible: bool
    provision_posted_cents: int
    notes: list[str]


class ProvisionRequest(ApiModel):
    fiscal_year: int = Field(ge=2023, le=2100)
    amount_cents: int = Field(ge=1, le=100_000_000_000)
