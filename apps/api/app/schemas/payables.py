from datetime import date
from typing import Literal, Self
from uuid import UUID

from pydantic import Field, model_validator

from app.schemas.payloads import ApiModel, TaxCategory

BillStatus = Literal["OPEN", "PARTIAL", "PAID", "VOID"]
SupplierPaymentMethod = Literal["cash", "transfer", "card", "cheque"]
SupplierPaymentStatus = Literal["POSTED", "ISSUED", "CLEARED", "VOID"]


class BillLineIn(ApiModel):
    product_id: UUID | None = None
    description: str = Field(min_length=1, max_length=200)
    quantity: int = Field(ge=1, le=1_000_000)
    # Excluding VAT, per unit.
    unit_cost_cents: int = Field(ge=0, le=100_000_000)
    tax_category: TaxCategory = "STANDARD"


class BillCreate(ApiModel):
    supplier_id: UUID
    store_id: UUID
    number: str = Field(min_length=1, max_length=40)
    bill_date: date
    due_date: date | None = None
    lines: list[BillLineIn] = Field(min_length=1, max_length=500)
    note: str = Field(default="", max_length=255)


class BillFromReceipt(ApiModel):
    """A bill for stock already received: a purchase-order receipt or an imported purchase batch."""

    goods_receipt_id: UUID | None = None
    purchase_batch_id: UUID | None = None
    number: str = Field(min_length=1, max_length=40)
    bill_date: date
    due_date: date | None = None
    # Needed only when the order or batch is not linked to a supplier.
    supplier_id: UUID | None = None
    note: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.goods_receipt_id is None) == (self.purchase_batch_id is None):
            raise ValueError("Give either a goods receipt or a purchase batch.")
        return self


class BillLineOut(ApiModel):
    id: UUID
    product_id: UUID | None
    description: str
    quantity: int
    unit_cost_cents: int
    tax_category: TaxCategory
    tax_cents: int
    line_total_cents: int


class BillOut(ApiModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str
    store_id: UUID
    store_code: str
    number: str
    purchase_order_number: str | None
    goods_receipt_number: str | None
    bill_date: date
    due_date: date
    currency: str
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    paid_cents: int
    balance_cents: int
    status: BillStatus
    overdue_days: int
    note: str
    lines: list[BillLineOut]


class ChequeOut(ApiModel):
    number: str = Field(min_length=1, max_length=32)
    bank: str = Field(min_length=1, max_length=80)
    cheque_date: date


class AllocationIn(ApiModel):
    bill_id: UUID
    amount_cents: int = Field(ge=1)


class SupplierPaymentCreate(ApiModel):
    """Leave allocations empty to settle the oldest due bills first; anything left stays as credit."""

    supplier_id: UUID
    amount_cents: int = Field(ge=1, le=10_000_000_000)
    method: SupplierPaymentMethod
    reference: str = Field(default="", max_length=64)
    paid_on: date
    cheque: ChequeOut | None = None
    allocations: list[AllocationIn] | None = Field(default=None, max_length=200)
    note: str = Field(default="", max_length=255)

    @model_validator(mode="after")
    def cheque_details(self) -> Self:
        if (self.method == "cheque") != (self.cheque is not None):
            raise ValueError("Cheque payments need the cheque number, bank and date; other methods must not send them.")
        if self.allocations and sum(item.amount_cents for item in self.allocations) > self.amount_cents:
            raise ValueError("Allocations cannot exceed the payment.")
        return self


class AllocationOut(ApiModel):
    bill_id: UUID
    bill_number: str
    amount_cents: int


class SupplierPaymentOut(ApiModel):
    id: UUID
    supplier_id: UUID
    supplier_name: str
    amount_cents: int
    currency: str
    method: SupplierPaymentMethod
    reference: str
    paid_on: date
    cheque_number: str | None
    cheque_bank: str | None
    cheque_date: date | None
    status: SupplierPaymentStatus
    note: str
    allocations: list[AllocationOut]
    unallocated_cents: int


class SupplierTerms(ApiModel):
    payment_terms_days: int = Field(ge=0, le=365)
    trn: str | None = Field(default=None, pattern=r"^\d{15}$")


class SupplierBalance(ApiModel):
    supplier_id: UUID
    name: str
    code: str
    trn: str | None
    payment_terms_days: int
    open_bills: int
    outstanding_cents: int
    overdue_cents: int
    due_7d_cents: int
    credit_cents: int
    cheques_issued_cents: int


class PayablesSummary(ApiModel):
    outstanding_cents: int
    overdue_cents: int
    due_7d_cents: int
    cheques_issued_cents: int
    suppliers: list[SupplierBalance]


class StatementRow(ApiModel):
    on: date
    kind: Literal["BILL", "PAYMENT"]
    reference: str
    bill_cents: int
    paid_cents: int
    balance_cents: int
    note: str


class PayablesAging(ApiModel):
    current: int
    days_1_30: int
    days_31_60: int
    days_61_90: int
    days_90_plus: int


class SupplierStatement(ApiModel):
    supplier: SupplierBalance
    currency: str
    rows: list[StatementRow]
    aging: PayablesAging
    open_bills: list[BillOut]


class UnbilledReceipt(ApiModel):
    goods_receipt_id: UUID | None
    purchase_batch_id: UUID | None = None
    number: str
    purchase_order_number: str
    supplier_id: UUID | None
    supplier_name: str
    store_code: str
    received_on: date
    units: int
    value_cents: int
