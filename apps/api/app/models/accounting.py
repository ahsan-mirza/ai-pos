from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

ACCOUNT_TYPES = ("ASSET", "LIABILITY", "EQUITY", "INCOME", "EXPENSE")


class GlAccount(TenantScoped, TimestampMixin, Base):
    """A general-ledger account. System accounts are the ones the posting engine maps documents to."""

    __tablename__ = "gl_accounts"
    __table_args__ = (
        tenant_unique("code", name="uq_gl_accounts_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(16))
    name: Mapped[str] = mapped_column(String(120))
    # ASSET, LIABILITY, EQUITY, INCOME, EXPENSE
    type: Mapped[str] = mapped_column(String(10), index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class JournalEntry(TenantScoped, Base):
    """A balanced journal entry. Entries are never edited: a change is a reversal plus a new entry.

    Automatic entries carry source_ref (the document, e.g. "sale:<id>") and a fingerprint of their lines; only one
    entry per source is active at a time. original_date is the document's date when the books were already locked
    for it and the entry had to post into the first open day."""

    __tablename__ = "journal_entries"
    __table_args__ = (
        tenant_unique("number", name="uq_journal_entries_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    number: Mapped[int] = mapped_column(Integer)
    entry_date: Mapped[date] = mapped_column(Date, index=True)
    original_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # SALES, COGS, RETURNS, RECEIPTS, STOCK, PURCHASES, PAYMENTS, EXPENSES, TRADEINS, PAYROLL, BANK, CHEQUES,
    # MANUAL, CLOSING, REVERSAL
    journal: Mapped[str] = mapped_column(String(12), index=True)
    reference: Mapped[str] = mapped_column(String(80), default="")
    memo: Mapped[str] = mapped_column(String(255), default="")
    source_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entries.id"), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lines: Mapped[list[JournalLine]] = relationship(
        back_populates="entry", cascade="all, delete-orphan", order_by="JournalLine.position", lazy="selectin"
    )


class JournalLine(TenantScoped, Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("debit_cents >= 0 AND credit_cents >= 0", name="journal_line_nonnegative"),
        CheckConstraint("(debit_cents = 0) <> (credit_cents = 0)", name="journal_line_one_side"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("gl_accounts.id"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    debit_cents: Mapped[int] = mapped_column(Integer, default=0)
    credit_cents: Mapped[int] = mapped_column(Integer, default=0)
    memo: Mapped[str] = mapped_column(String(255), default="")
    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
