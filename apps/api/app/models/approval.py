from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class ApprovalRequest(TimestampMixin, Base):
    """A register asking for a manager's approval remotely (price override, below-floor sale, credit limit,
    refund). The manager approves from the portal or phone; the register then records that manager as the
    approver on the sale, exactly as if they had typed their PIN at the till."""

    __tablename__ = "approval_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # PRICE_OVERRIDE, BELOW_FLOOR, CREDIT_LIMIT, REFUND
    kind: Mapped[str] = mapped_column(String(16), index=True)
    permission: Mapped[str] = mapped_column(String(64))
    store_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), nullable=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(160))
    details: Mapped[list[str]] = mapped_column(JSON, default=list)
    amount_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # PENDING, APPROVED, DECLINED, CANCELLED, EXPIRED
    status: Mapped[str] = mapped_column(String(10), default="PENDING", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str] = mapped_column(String(250), default="")
