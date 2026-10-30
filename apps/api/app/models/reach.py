"""AxizReach: one engagement add-on, three channels, campaigns queued onto the existing outbox."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class MessagingChannel(TenantScoped, TimestampMixin, Base):
    """Tenant-owned channel. Secrets stay encrypted; the API only returns a masked hint."""

    __tablename__ = "messaging_channels"
    __table_args__ = (tenant_unique("channel", name="uq_messaging_channels_channel"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(12))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    provider: Mapped[str] = mapped_column(String(24), default="log")
    public_config: Mapped[dict] = mapped_column(JSON, default=dict)
    secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="not_configured")
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReachCampaign(TenantScoped, TimestampMixin, Base):
    __tablename__ = "reach_campaigns"
    __table_args__ = (tenant_unique("idempotency_key", name="uq_reach_campaigns_idempotency"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500), default="")
    objective: Mapped[str] = mapped_column(String(40), default="promotion")
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)
    audience: Mapped[dict] = mapped_column(JSON, default=dict)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    eligible_count: Mapped[int] = mapped_column(Integer, default=0)
    suppressed_count: Mapped[int] = mapped_column(Integer, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, default=0)


class ReachUsage(TenantScoped, Base):
    """One billable unit per outbound message. The unique message id stops a retry from charging twice."""

    __tablename__ = "reach_usage"
    __table_args__ = (tenant_unique("outbound_message_id", name="uq_reach_usage_message"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    outbound_message_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("outbound_messages.id"))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reach_campaigns.id"), nullable=True, index=True
    )
    channel: Mapped[str] = mapped_column(String(12))
    purpose: Mapped[str] = mapped_column(String(16), default="marketing")
    units: Mapped[int] = mapped_column(Integer, default=1)
    cost_cents: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
