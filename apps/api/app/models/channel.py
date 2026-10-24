"""Delivery channels: apps (Talabat, Deliveroo, Careem, or any provider speaking the generic format) that send orders
by signed webhook or are keyed in at the register, and the payouts they settle with the business."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class DeliveryChannel(TenantScoped, TimestampMixin, Base):
    __tablename__ = "delivery_channels"
    __table_args__ = (
        tenant_unique("code", name="uq_delivery_channels_code"),
        CheckConstraint("commission_bps >= 0 AND commission_bps <= 10000", name="commission_range"),
        CheckConstraint("price_markup_bps >= 0", name="markup_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60))
    # In the webhook URL: /api/v1/channels/{code}/orders.
    code: Mapped[str] = mapped_column(String(32))
    # The branch its orders arrive at.
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    # How webhook bodies are read: "generic" (the normalised format) until named provider adapters ship.
    adapter: Mapped[str] = mapped_column(String(20), default="generic")
    commission_bps: Mapped[int] = mapped_column(Integer, default=0)
    # Menu prices on the app above the till price (e.g. 1500 = +15%), applied to items the webhook does not price.
    price_markup_bps: Mapped[int] = mapped_column(Integer, default=0)
    # HMAC-SHA256 key for X-Channel-Signature, encrypted at rest.
    webhook_secret: Mapped[str] = mapped_column(String(500))
    auto_accept: Mapped[bool] = mapped_column(Boolean, default=False)
    default_prep_minutes: Mapped[int] = mapped_column(Integer, default=20)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Webhook orders are opened in this user's name (whoever set the channel up).
    created_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))


class ChannelPayout(TenantScoped, Base):
    """Money a channel paid out for its orders: what landed in the bank and the commission it kept."""

    __tablename__ = "channel_payouts"
    __table_args__ = (
        CheckConstraint("amount_cents >= 0", name="amount_nonnegative"),
        CheckConstraint("commission_cents >= 0", name="commission_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_channels.id", ondelete="CASCADE"), index=True
    )
    amount_cents: Mapped[int] = mapped_column(Integer)
    commission_cents: Mapped[int] = mapped_column(Integer, default=0)
    reference: Mapped[str | None] = mapped_column(String(80), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
