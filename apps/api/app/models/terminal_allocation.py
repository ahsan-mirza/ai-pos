"""Terminal stock allocation. This is a reservation, not a second on-hand ledger.

`inventory_levels` and `stock_movements` stay authoritative. Issuing an allocation increases
`quantity_reserved`. A posted sale releases that hold and then uses the existing movement service.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

HOLDING_STATUSES = ("ACTIVE", "QUARANTINED")
ALLOCATION_STATUSES = ("ACTIVE", "EXHAUSTED", "RELEASED", "QUARANTINED")


class TerminalAllocation(TenantScoped, TimestampMixin, Base):
    __tablename__ = "terminal_allocations"
    __table_args__ = (
        CheckConstraint("quantity_allocated > 0", name="ck_terminal_allocations_allocated_positive"),
        CheckConstraint("quantity_consumed >= 0", name="ck_terminal_allocations_consumed_nonnegative"),
        CheckConstraint(
            "quantity_consumed <= quantity_allocated",
            name="ck_terminal_allocations_consumed_within",
        ),
        CheckConstraint(
            "status IN ('ACTIVE', 'EXHAUSTED', 'RELEASED', 'QUARANTINED')",
            name="ck_terminal_allocations_status",
        ),
        tenant_unique("manifest_id", name="uq_terminal_allocations_manifest"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    manifest_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), default=uuid.uuid4)
    version: Mapped[int] = mapped_column(Integer, default=1)
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    device_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("devices.id"), index=True)
    device_thumbprint: Mapped[str] = mapped_column(String(64))
    product_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("products.id"), index=True)
    serial_number_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("serial_numbers.id"), nullable=True, index=True
    )
    batch_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("batch_items.id"), nullable=True, index=True
    )
    unit: Mapped[str] = mapped_column(String(16), default="each")
    quantity_allocated: Mapped[int] = mapped_column(Integer)
    quantity_consumed: Mapped[int] = mapped_column(Integer, default=0)
    last_sequence: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE", index=True)
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    signing_key_id: Mapped[str] = mapped_column(String(64))
    manifest_payload: Mapped[str] = mapped_column(Text)
    manifest_signature: Mapped[str] = mapped_column(Text)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    @property
    def remaining(self) -> int:
        return self.quantity_allocated - self.quantity_consumed


class TerminalAllocationConsumption(TenantScoped, Base):
    """One accepted consumption. The sale idempotency key is stored so a replay is not a second draw."""

    __tablename__ = "terminal_allocation_consumptions"
    __table_args__ = (
        CheckConstraint("sequence > 0", name="ck_terminal_allocation_consumptions_sequence"),
        CheckConstraint("quantity > 0", name="ck_terminal_allocation_consumptions_quantity"),
        tenant_unique("allocation_id", "sequence", name="uq_terminal_allocation_consumptions_sequence"),
        tenant_unique("idempotency_key", name="uq_terminal_allocation_consumptions_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("terminal_allocations.id"), index=True
    )
    sequence: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)
    sale_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
