from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped


class QuotePayment(TenantScoped, Base):
    """A deposit taken against a layaway. Applied as a `deposit` tender when the layaway converts to a sale."""

    __tablename__ = "quote_payments"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="quote_payment_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    quote_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(Integer)
    method: Mapped[str] = mapped_column(String(16))
    reference: Mapped[str] = mapped_column(String(120), default="")
    received_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    shift_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    # ACTIVE until the layaway converts (APPLIED) or is cancelled with the money owed back (REFUND_DUE).
    status: Mapped[str] = mapped_column(String(12), default="ACTIVE")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
