from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class MessageTemplate(TenantScoped, TimestampMixin, Base):
    """Editable text for a customer message. {{placeholders}} are filled from the event's context."""

    __tablename__ = "message_templates"
    __table_args__ = (
        tenant_unique("key", name="uq_message_templates_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(48))
    name: Mapped[str] = mapped_column(String(120))
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class OutboundMessage(TenantScoped, Base):
    """The outbox. Rows are queued by business events and sent by the dispatch job through a provider."""

    __tablename__ = "outbound_messages"
    __table_args__ = (
        tenant_unique("dedupe_key", name="uq_outbound_messages_dedupe_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(12), index=True)
    to_address: Mapped[str] = mapped_column(String(254))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True
    )
    template_key: Mapped[str | None] = mapped_column(String(48), nullable=True)
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text)
    # QUEUED -> SENT | FAILED (after retries) | SKIPPED (no consent or no address)
    status: Mapped[str] = mapped_column(String(12), default="QUEUED", index=True)
    provider: Mapped[str | None] = mapped_column(String(24), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attachment_kind: Mapped[str | None] = mapped_column(String(24), nullable=True)
    attachment_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
