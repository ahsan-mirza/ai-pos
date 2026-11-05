"""Customer-care rows. Customers, products, stock, and the outbox stay in core."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow


class ReachAiAgent(TenantScoped, TimestampMixin, Base):
    """One configuration for this business. Replies stay off until the owner enables them."""

    __tablename__ = "reach_ai_agents"
    __table_args__ = (tenant_unique("slot", name="uq_reach_ai_agents_slot"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slot: Mapped[str] = mapped_column(String(16), default="default")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    mode: Mapped[str] = mapped_column(String(16), default="hybrid")
    name: Mapped[str] = mapped_column(String(80), default="Store assistant")
    greeting: Mapped[str] = mapped_column(String(300), default="Hello. How can we help?")
    language: Mapped[str] = mapped_column(String(8), default="auto")
    tone: Mapped[str] = mapped_column(String(24), default="professional")
    instructions: Mapped[str] = mapped_column(Text, default="")
    product_help: Mapped[bool] = mapped_column(Boolean, default=True)
    order_help: Mapped[bool] = mapped_column(Boolean, default=True)
    action_detection: Mapped[bool] = mapped_column(Boolean, default=True)
    handoff: Mapped[bool] = mapped_column(Boolean, default=True)


class ReachAiKnowledge(TenantScoped, TimestampMixin, Base):
    """Approved text the agent may quote. Live prices and stock are not stored here."""

    __tablename__ = "reach_ai_knowledge"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kind: Mapped[str] = mapped_column(String(16), default="faq")
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="ready")


class ReachAiConversation(TenantScoped, TimestampMixin, Base):
    __tablename__ = "reach_ai_conversations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    connection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("reach_connections.id"), index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("customers.id"), nullable=True)
    phone: Mapped[str] = mapped_column(String(32), index=True)
    customer_name: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    handler: Mapped[str] = mapped_column(String(8), default="ai")
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    language: Mapped[str] = mapped_column(String(8), default="en")
    intent: Mapped[str] = mapped_column(String(24), default="")
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    unread_count: Mapped[int] = mapped_column(Integer, default=0)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_preview: Mapped[str] = mapped_column(String(180), default="")


class ReachAiMessage(TenantScoped, Base):
    __tablename__ = "reach_ai_messages"
    __table_args__ = (
        tenant_unique("provider_message_id", name="uq_reach_ai_messages_provider"),
        tenant_unique("reply_to_id", name="uq_reach_ai_messages_reply"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reach_ai_conversations.id"), index=True
    )
    reply_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    direction: Mapped[str] = mapped_column(String(8))
    author: Mapped[str] = mapped_column(String(12))
    body: Mapped[str] = mapped_column(Text, default="")
    provider_message_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outbound_message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("outbound_messages.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="received", index=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReachAiAction(TenantScoped, TimestampMixin, Base):
    """A request for staff. Completing one does not post a sale, refund, or stock change by itself."""

    __tablename__ = "reach_ai_actions"
    __table_args__ = (tenant_unique("dedupe_key", name="uq_reach_ai_actions_dedupe"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reach_ai_conversations.id"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reach_ai_messages.id"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(80))
    category: Mapped[str] = mapped_column(String(24))
    title: Mapped[str] = mapped_column(String(160))
    details: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(8), default="normal")
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    consequential: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    result: Mapped[str] = mapped_column(String(500), default="")


class ReachAiEvent(TenantScoped, Base):
    __tablename__ = "reach_ai_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    action_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(String(500), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ReachAiUsage(TenantScoped, Base):
    __tablename__ = "reach_ai_usage"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    kind: Mapped[str] = mapped_column(String(16))
    provider: Mapped[str] = mapped_column(String(40), default="template")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
