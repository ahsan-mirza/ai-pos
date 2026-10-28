from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique


class Device(TenantScoped, TimestampMixin, Base):
    """A registered register. Its key is shown once at creation; only a SHA-256 of the 256-bit key is stored."""

    __tablename__ = "devices"
    __table_args__ = (
        tenant_unique("key_hash", name="uq_devices_key_hash"),
        tenant_unique("store_id", "code", name="uq_devices_store_code"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    code: Mapped[str] = mapped_column(String(12))
    name: Mapped[str] = mapped_column(String(80))
    key_hash: Mapped[str] = mapped_column(String(64))
    key_hint: Mapped[str] = mapped_column(String(12))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # The business-settings generation this register last applied. Behind the current generation means pending.
    entitlement_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entitlement_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)


class DeviceActivation(TenantScoped, TimestampMixin, Base):
    """One-time key a manager hands to a new register; exchanging it issues the register's device token."""

    __tablename__ = "device_activations"
    __table_args__ = (
        tenant_unique("code_hash", name="uq_device_activations_code_hash"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    device_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_machine: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
