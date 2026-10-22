from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class BankAccount(TimestampMixin, Base):
    __tablename__ = "bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    bank: Mapped[str] = mapped_column(String(80))
    iban: Mapped[str | None] = mapped_column(String(34), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BankStatement(TimestampMixin, Base):
    """One imported statement file."""

    __tablename__ = "bank_statements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    # CSV or MT940
    file_format: Mapped[str] = mapped_column(String(8))
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    lines_imported: Mapped[int] = mapped_column(Integer, default=0)
    lines_skipped: Mapped[int] = mapped_column(Integer, default=0)
    imported_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class BankStatementLine(TimestampMixin, Base):
    """A bank statement line. amount_cents is signed: money into the account is positive. A matched line points at
    one book record by key (e.g. "card:<store>:<date>", "supplier_payment:<id>"); fee_cents is a card-terminal fee
    the bank kept, booked as a bank-fee expense when the line was matched."""

    __tablename__ = "bank_statement_lines"
    __table_args__ = (
        UniqueConstraint("account_id", "line_hash", name="uq_bank_statement_lines_hash"),
        UniqueConstraint("account_id", "matched_key", name="uq_bank_statement_lines_matched"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_accounts.id"), index=True)
    statement_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("bank_statements.id"), index=True)
    booked_on: Mapped[date] = mapped_column(Date, index=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    reference: Mapped[str] = mapped_column(String(80), default="")
    amount_cents: Mapped[int] = mapped_column(Integer)
    balance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_hash: Mapped[str] = mapped_column(String(64))
    # UNMATCHED, MATCHED, IGNORED
    status: Mapped[str] = mapped_column(String(10), default="UNMATCHED", index=True)
    matched_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    matched_label: Mapped[str] = mapped_column(String(160), default="")
    fee_cents: Mapped[int] = mapped_column(Integer, default=0)
    fee_expense_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("expenses.id"), nullable=True
    )
    # AUTO or the user who matched / ignored it
    matched_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    match_note: Mapped[str] = mapped_column(String(255), default="")
