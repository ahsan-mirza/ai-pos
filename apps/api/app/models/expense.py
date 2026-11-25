from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

EXPENSE_CATEGORIES = (
    "RENT",
    "UTILITIES",
    "SALARIES",
    "TRANSPORT",
    "MARKETING",
    "MAINTENANCE",
    "OFFICE",
    "BANK_FEES",
    "OTHER",
)


class Expense(TenantScoped, TimestampMixin, Base):
    """A business expense paid outside supplier bills: petty cash, card or bank. total = net + tax; the tax is
    recoverable input VAT only when the business holds a valid tax invoice for it."""

    __tablename__ = "expenses"
    __table_args__ = (
        tenant_unique("number", name="uq_expenses_number"),
        tenant_unique("client_key", name="uq_expenses_client_key"),
        CheckConstraint("total_cents > 0", name="expense_total_positive"),
        CheckConstraint("tax_cents >= 0 AND tax_cents < total_cents", name="expense_tax_within_total"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(40))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    category: Mapped[str] = mapped_column(String(32), index=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expense_categories.id"), nullable=True, index=True
    )
    description: Mapped[str] = mapped_column(String(200))
    payee: Mapped[str] = mapped_column(String(120), default="")
    payee_trn: Mapped[str | None] = mapped_column(String(15), nullable=True)
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("suppliers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    spent_on: Mapped[date] = mapped_column(Date, index=True)
    net_cents: Mapped[int] = mapped_column(Integer)
    tax_cents: Mapped[int] = mapped_column(Integer, default=0)
    total_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    has_tax_invoice: Mapped[bool] = mapped_column(Boolean, default=False)
    # PETTY_CASH, BANK, CARD
    paid_from: Mapped[str] = mapped_column(String(12))
    reference: Mapped[str] = mapped_column(String(64), default="")
    client_key: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # RECORDED or VOID
    status: Mapped[str] = mapped_column(String(8), default="RECORDED", index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    voided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    void_reason: Mapped[str] = mapped_column(String(255), default="")


class PettyCashEntry(TenantScoped, Base):
    """Append-only petty cash ledger per branch. amount_cents is signed: top-ups add, expenses subtract."""

    __tablename__ = "petty_cash_entries"
    __table_args__ = (CheckConstraint("amount_cents <> 0", name="petty_cash_nonzero"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # TOPUP, EXPENSE, VOID (an expense reversed), COUNT (a counted correction)
    kind: Mapped[str] = mapped_column(String(8))
    amount_cents: Mapped[int] = mapped_column(Integer)
    balance_after: Mapped[int] = mapped_column(Integer)
    expense_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("expenses.id"), nullable=True)
    # For top-ups: where the cash came from (bank or till).
    source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ExpenseCategory(TenantScoped, TimestampMixin, Base):
    """A tenant expense type. The original nine codes stay so older expenses keep their meaning."""

    __tablename__ = "expense_categories"
    __table_args__ = (
        tenant_unique("code", name="uq_expense_categories_code"),
        tenant_unique("name_key", name="uq_expense_categories_name_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(80))
    name_key: Mapped[str] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(String(200), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=100)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class ExpenseAttachment(TenantScoped, Base):
    """The compressed bill image for one expense. Bytes live under storage/expense-bills, not in this row."""

    __tablename__ = "expense_attachments"
    __table_args__ = (tenant_unique("expense_id", name="uq_expense_attachments_expense"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    expense_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expenses.id", ondelete="CASCADE"), index=True
    )
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(160))
    content_type: Mapped[str] = mapped_column(String(80))
    original_size_bytes: Mapped[int] = mapped_column(Integer)
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(180))
    checksum: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(12), default="STORED")
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
