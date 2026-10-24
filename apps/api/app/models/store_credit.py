from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique

CREDIT_KINDS = ("VOUCHER", "GIFT_CARD")


class StoreCredit(TenantScoped, TimestampMixin, Base):
    __tablename__ = "store_credits"
    __table_args__ = (
        tenant_unique("code", name="uq_store_credits_code"),
        CheckConstraint("initial_cents >= 1", name="initial_positive"),
        CheckConstraint("balance_cents >= 0", name="balance_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(32))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    # Vouchers come from a refund (return_id) or a trade-in paid out as store credit (no return).
    return_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("returns.id"), index=True, nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3))
    initial_cents: Mapped[int] = mapped_column(Integer)
    balance_cents: Mapped[int] = mapped_column(Integer)
    # VOUCHER: refund or trade-in credit (store_credit tender). GIFT_CARD: sold or issued as a gift (gift_card tender).
    kind: Mapped[str] = mapped_column(String(16), default="VOUCHER", index=True)
    issued_sale_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sales.id"), nullable=True, index=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(255), default="")


class StoreCreditRedemption(TenantScoped, TimestampMixin, Base):
    """Append-only: each sale that spent part of a voucher. balance_cents = initial_cents - sum(amount_cents)."""

    __tablename__ = "store_credit_redemptions"
    __table_args__ = (
        CheckConstraint("amount_cents >= 1", name="amount_positive"),
        tenant_unique("store_credit_id", "sale_id", name="uq_store_credit_redemption_sale"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_credit_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("store_credits.id"), index=True)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("sales.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    amount_cents: Mapped[int] = mapped_column(Integer)
