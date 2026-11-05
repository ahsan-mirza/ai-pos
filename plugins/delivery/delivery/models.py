"""Tenant-owned marketplace connection. Orders and payouts stay on the existing channel tables."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class DeliveryConnection(TenantScoped, TimestampMixin, Base):
    """One provider setup for one branch. Credentials never leave the server."""

    __tablename__ = "delivery_connections"
    __table_args__ = (tenant_unique("provider_code", "store_id", name="uq_delivery_connections_provider_store"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider_code: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(8), default="")
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    channel_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("delivery_channels.id"), nullable=True
    )
    credential_encrypted: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
