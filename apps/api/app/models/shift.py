from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class RegisterShift(TimestampMixin, Base):
    """A cashier session on one register, from opening float to the Z report. Created offline by the register."""

    __tablename__ = "register_shifts"
    __table_args__ = (CheckConstraint("opening_float_cents >= 0", name="opening_float_nonnegative"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    opened_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    closed_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(12), default="OPEN", index=True)
    opening_float_cents: Mapped[int] = mapped_column(Integer)
    counted_cash_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    expected_cash_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    variance_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    blind_close: Mapped[bool] = mapped_column(Boolean, default=True)
    z_number: Mapped[str | None] = mapped_column(String(40), unique=True, nullable=True)
    report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")


class CashMovement(Base):
    """Cash in or out of a drawer outside a sale: pay-ins, pay-outs, drops to the safe, and no-sale opens."""

    __tablename__ = "cash_movements"
    __table_args__ = (CheckConstraint("amount_cents >= 0", name="cash_movement_nonnegative"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    shift_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("register_shifts.id"), index=True)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"))
    kind: Mapped[str] = mapped_column(String(16))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    reason: Mapped[str] = mapped_column(String(250), default="")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
