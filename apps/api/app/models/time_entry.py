from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class TimeEntry(TimestampMixin, Base):
    """One clocked stretch of work. Registers create it at clock-in (OPEN) and close it at clock-out; a manager may
    correct it with a note and then APPROVE it, after which payroll uses it and nothing changes it."""

    __tablename__ = "time_entries"
    __table_args__ = (CheckConstraint("break_minutes >= 0", name="time_entry_break_nonnegative"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    clock_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    clock_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    break_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # register or portal
    source: Mapped[str] = mapped_column(String(10), default="register")
    # OPEN, CLOSED, APPROVED
    status: Mapped[str] = mapped_column(String(10), default="OPEN", index=True)
    edited_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    edit_note: Mapped[str] = mapped_column(String(255), default="")
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
