"""Requests for a lost terminal or a quarantined sync conflict.

Approval records the decision. It does not post stock or money. Those postings stay
awaiting an owner policy.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin


class LostTerminalRequest(TenantScoped, TimestampMixin, Base):
    __tablename__ = "lost_terminal_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    allocation_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    posting_status: Mapped[str] = mapped_column(String(32), default="awaiting_approval")
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConflictAdjustmentRequest(TenantScoped, TimestampMixin, Base):
    __tablename__ = "conflict_adjustment_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), index=True)
    original_hash: Mapped[str] = mapped_column(String(128))
    proposed_hash: Mapped[str] = mapped_column(String(128))
    currency: Mapped[str] = mapped_column(String(3))
    amount_cents: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[str] = mapped_column(Text, default="")
    request_key: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), default="submitted")
    posting_status: Mapped[str] = mapped_column(String(32), default="awaiting_approval")
    submitted_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
