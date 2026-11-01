"""Reach tables. Customer rows and the messaging outbox stay in core."""

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


class ReachConnection(TenantScoped, TimestampMixin, Base):
    """One Evolution session for this store. The webhook key is unguessable and is not a tenant id."""

    __tablename__ = "reach_connections"
    __table_args__ = (
        tenant_unique("instance_name", name="uq_reach_connections_instance"),
        tenant_unique("webhook_key", name="uq_reach_connections_webhook"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(80))
    instance_name: Mapped[str] = mapped_column(String(80))
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="created")
    webhook_key: Mapped[str] = mapped_column(String(80))
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)


class ReachRecipient(TenantScoped, TimestampMixin, Base):
    """One person on one campaign. Provider acceptance is `sent`; delivery and read come from webhooks."""

    __tablename__ = "reach_recipients"
    __table_args__ = (tenant_unique("outbound_message_id", name="uq_reach_recipients_message"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    campaign_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reach_campaigns.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outbound_messages.id"), nullable=True
    )
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reach_connections.id"), nullable=True
    )
    phone: Mapped[str] = mapped_column(String(254), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReachTemplate(TenantScoped, TimestampMixin, Base):
    __tablename__ = "reach_templates"
    __table_args__ = (tenant_unique("name", name="uq_reach_templates_name"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120))
    channel: Mapped[str] = mapped_column(String(12), default="whatsapp")
    body: Mapped[str] = mapped_column(Text)
    media_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)


class ReachCreditAccount(TenantScoped, TimestampMixin, Base):
    """Integer prepaid balance. `reserved` is held for campaigns that have not been accepted yet."""

    __tablename__ = "reach_credit_accounts"
    __table_args__ = (tenant_unique("purpose", name="uq_reach_credit_accounts_purpose"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purpose: Mapped[str] = mapped_column(String(24), default="marketing")
    balance: Mapped[int] = mapped_column(Integer, default=0)
    reserved: Mapped[int] = mapped_column(Integer, default=0)


class ReachCreditTransaction(TenantScoped, Base):
    """Append-only ledger. Rows are never updated."""

    __tablename__ = "reach_credit_transactions"
    __table_args__ = (tenant_unique("idempotency_key", name="uq_reach_credit_tx_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reach_credit_accounts.id"))
    kind: Mapped[str] = mapped_column(String(16))
    units: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReachWebhookEvent(TenantScoped, Base):
    __tablename__ = "reach_webhook_events"
    __table_args__ = (tenant_unique("event_key", name="uq_reach_webhook_events_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reach_connections.id"))
    event_key: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(48), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
