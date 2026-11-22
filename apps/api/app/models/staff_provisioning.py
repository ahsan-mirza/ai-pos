"""Staff provisioning events. These are not sales and they are not rows in sync_queue."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, tenant_unique, utcnow


class StaffProvisioningEvent(TenantScoped, Base):
    __tablename__ = "staff_provisioning_events"
    __table_args__ = (tenant_unique("event_id", name="uq_staff_provisioning_event"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[str] = mapped_column(String(64))
    operation: Mapped[str] = mapped_column(String(16))
    payload_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    safe_message: Mapped[str] = mapped_column(Text, default="")
    origin_terminal_id: Mapped[str] = mapped_column(String(64), default="")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    base_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
