from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Cheque(TimestampMixin, Base):
    """A customer's cheque, usually post-dated (PDC), from a till tender or an account payment.

    The payment is booked when the cheque is received; a bounce or cancellation reverses it on the account."""

    __tablename__ = "cheques"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="cheque_amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    cheque_number: Mapped[str] = mapped_column(String(32))
    bank: Mapped[str] = mapped_column(String(80))
    cheque_date: Mapped[date] = mapped_column(Date, index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    # RECEIVED -> DEPOSITED -> CLEARED, or BOUNCED / CANCELLED (both reverse the payment).
    status: Mapped[str] = mapped_column(String(12), default="RECEIVED", index=True)
    source: Mapped[str] = mapped_column(String(8))
    sale_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True)
    ledger_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customer_ledger_entries.id"), nullable=True
    )
    received_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    bounce_fee_cents: Mapped[int] = mapped_column(Integer, default=0)


class ChequeEvent(Base):
    """Append-only status history of a cheque."""

    __tablename__ = "cheque_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cheque_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("cheques.id"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(12), nullable=True)
    to_status: Mapped[str] = mapped_column(String(12))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
