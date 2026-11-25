from datetime import date, datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, TaxCategory

ExpenseCategory = Literal[
    "RENT", "UTILITIES", "SALARIES", "TRANSPORT", "MARKETING", "MAINTENANCE", "OFFICE", "BANK_FEES", "OTHER"
]
PaidFrom = Literal["PETTY_CASH", "BANK", "CARD"]


class ExpenseBillIn(ApiModel):
    file_name: str = Field(default="bill", max_length=160)
    content_type: str = Field(max_length=80)
    data_base64: str


class ExpenseCreate(ApiModel):
    """total_cents is what was paid, VAT included. Leave tax_cents empty to work it out from tax_category."""

    store_id: UUID
    category: str | None = Field(default=None, max_length=32)
    category_id: UUID | None = None
    description: str = Field(min_length=2, max_length=200)
    payee: str = Field(default="", max_length=120)
    payee_trn: str | None = Field(default=None, pattern=r"^\d{15}$")
    supplier_id: UUID | None = None
    spent_on: date
    total_cents: int = Field(ge=1, le=1_000_000_000)
    tax_category: TaxCategory = "STANDARD"
    tax_cents: int | None = Field(default=None, ge=0)
    has_tax_invoice: bool = False
    paid_from: PaidFrom
    reference: str = Field(default="", max_length=64)
    client_key: str | None = Field(default=None, max_length=80, pattern=r"^[A-Za-z0-9:_.-]{8,80}$")
    bill: ExpenseBillIn | None = None

    @model_validator(mode="after")
    def tax_below_total(self) -> Self:
        if self.category_id is None and not (self.category or "").strip():
            raise ValueError("Select an expense category.")
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
    category: str
    category_id: UUID | None
    category_name: str
    description: str
    payee: str
    payee_trn: str | None
    supplier_id: UUID | None
    supplier_name: str
    supplier_code: str
    spent_on: date
    net_cents: int
    tax_cents: int
    recoverable_tax_cents: int
    total_cents: int
    currency: str
    has_tax_invoice: bool
    has_bill: bool
    paid_from: PaidFrom
    reference: str
    status: Literal["RECORDED", "VOID"]
    created_by_name: str | None
    void_reason: str


class ExpenseCategoryIn(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=200)


class ExpenseCategoryOut(ApiModel):
    id: UUID
    code: str
    name: str
    description: str
    is_active: bool
    sort_order: int


class ExpenseBillOut(ApiModel):
    file_name: str
    content_type: str
    original_size_bytes: int
    size_bytes: int
    data_base64: str


class ExpenseSupplier(ApiModel):
    id: UUID
    name: str
    code: str
    phone: str | None
    trn: str | None
    is_active: bool


class CategoryTotal(ApiModel):
    category: str
    category_name: str
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
