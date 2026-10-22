from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, TaxCategory

ExpenseCategory = Literal[
    "RENT", "UTILITIES", "SALARIES", "TRANSPORT", "MARKETING", "MAINTENANCE", "OFFICE", "BANK_FEES", "OTHER"
]
PaidFrom = Literal["PETTY_CASH", "BANK", "CARD"]


class ExpenseCreate(ApiModel):
    """total_cents is what was paid, VAT included. Leave tax_cents empty to work it out from tax_category."""

    store_id: UUID
    category: ExpenseCategory
    description: str = Field(min_length=2, max_length=200)
    payee: str = Field(default="", max_length=120)
    payee_trn: str | None = Field(default=None, pattern=r"^\d{15}$")
    spent_on: date
    total_cents: int = Field(ge=1, le=1_000_000_000)
    tax_category: TaxCategory = "STANDARD"
    tax_cents: int | None = Field(default=None, ge=0)
    has_tax_invoice: bool = False
    paid_from: PaidFrom
    reference: str = Field(default="", max_length=64)

    @model_validator(mode="after")
    def tax_below_total(self) -> Self:
        if self.tax_cents is not None and self.tax_cents >= self.total_cents:
            raise ValueError("VAT must be less than the total paid.")
        return self


class ExpenseVoid(ApiModel):
    reason: str = Field(min_length=3, max_length=255)


class ExpenseOut(ApiModel):
    id: UUID
    number: str
    store_id: UUID
    store_code: str
    category: ExpenseCategory
    description: str
    payee: str
    payee_trn: str | None
    spent_on: date
    net_cents: int
    tax_cents: int
    recoverable_tax_cents: int
    total_cents: int
    currency: str
    has_tax_invoice: bool
    paid_from: PaidFrom
    reference: str
    status: Literal["RECORDED", "VOID"]
    created_by_name: str | None
    void_reason: str


class CategoryTotal(ApiModel):
    category: ExpenseCategory
    total_cents: int
    count: int


class ExpenseList(ApiModel):
    items: list[ExpenseOut]
    total_cents: int
    recoverable_tax_cents: int
    by_category: list[CategoryTotal]


class PettyCashTopUp(ApiModel):
    store_id: UUID
    amount_cents: int = Field(ge=1, le=100_000_000)
    source: Literal["bank", "till"]
    note: str = Field(default="", max_length=255)


class PettyCashCount(ApiModel):
    store_id: UUID
    counted_cents: int = Field(ge=0, le=100_000_000)
    note: str = Field(min_length=3, max_length=255)


class PettyCashEntryOut(ApiModel):
    id: UUID
    kind: Literal["TOPUP", "EXPENSE", "VOID", "COUNT"]
    amount_cents: int
    balance_after: int
    expense_number: str | None
    note: str
    user_name: str | None
    created_at: datetime


class PettyCashOut(ApiModel):
    store_id: UUID
    store_code: str
    balance_cents: int
    entries: list[PettyCashEntryOut]
