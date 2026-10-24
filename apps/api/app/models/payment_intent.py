from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, tenant_unique, utcnow


class PaymentIntent(TenantScoped, Base):
    """A payment the till asks a provider to collect: a QR the customer scans, an amount pushed to a card
    terminal, or a buy-now-pay-later checkout. The provider (webhook or poll) moves it to PAID; the sale then
    carries a tender pointing at it, and each intent pays for one sale only."""

    __tablename__ = "payment_intents"
    __table_args__ = (
        CheckConstraint("amount_cents > 0", name="intent_amount_positive"),
        CheckConstraint("refunded_cents >= 0 AND refunded_cents <= amount_cents", name="intent_refund_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # QR | CARD | BNPL: which tender method may consume it.
    channel: Mapped[str] = mapped_column(String(8), default="QR", server_default="QR", index=True)
    provider: Mapped[str] = mapped_column(String(16))
    terminal_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("payment_terminals.id"), nullable=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    reference: Mapped[str] = mapped_column(String(40))
    qr_payload: Mapped[str] = mapped_column(Text)
    # BNPL: the provider's checkout page the customer opens (shown as a QR or sent by SMS).
    customer_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    auth_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    card_brand: Mapped[str | None] = mapped_column(String(20), nullable=True)
    card_last4: Mapped[str | None] = mapped_column(String(4), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # PENDING -> AUTHORIZED (BNPL, before capture) -> PAID; or DECLINED | EXPIRED | CANCELLED
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True)
    refunded_cents: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentTerminal(TenantScoped, Base):
    """A card machine at a store, known to its provider by `terminal_ref` (N-Genius outlet/terminal id,
    Geidea terminal id). A till sends its card amounts to the terminal assigned to it, else the store's first."""

    __tablename__ = "payment_terminals"
    __table_args__ = (tenant_unique("provider", "terminal_ref", name="uq_payment_terminals_ref"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    terminal_ref: Mapped[str] = mapped_column(String(64))
    label: Mapped[str] = mapped_column(String(80))
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PaymentRefund(TenantScoped, Base):
    """Money sent back through the provider that took it. FAILED refunds are retried by a job and from the
    portal; the return itself is already recorded, so the customer's refund never waits on the provider."""

    __tablename__ = "payment_refunds"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="refund_amount_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    intent_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("payment_intents.id"), index=True)
    return_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("returns.id"), nullable=True, index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    # PENDING -> SUCCEEDED | FAILED (retryable)
    status: Mapped[str] = mapped_column(String(12), default="PENDING", index=True)
    provider_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
