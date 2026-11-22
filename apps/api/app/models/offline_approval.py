"""Requests for a lost-terminal write-off or a financial conflict adjustment.

Decisions are recorded. Posting stays disabled until a business policy says how
stock and money should move. posted_at remains empty.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin


class OfflineWriteoffRequest(TenantScoped, TimestampMixin, Base):
    __tablename__ = "offline_writeoff_requests"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    allocation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    requested_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    evidence: Mapped[str] = mapped_column(String(500), default="")
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OfflineConflictAdjustment(TenantScoped, TimestampMixin, Base):
    __tablename__ = "offline_conflict_adjustments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    original_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    requested_by_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    decision_note: Mapped[str] = mapped_column(String(500), default="")
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
