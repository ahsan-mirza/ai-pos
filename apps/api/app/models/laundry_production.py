"""Laundry production. Garments stay work items. These tables do not hold stock quantities."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TenantScoped, TimestampMixin, tenant_unique, utcnow

MACHINE_TYPES = ("WASHER", "DRYER", "DRY_CLEANING", "PRESS", "FOLDER", "OTHER")
MACHINE_STATUSES = ("AVAILABLE", "RUNNING", "MAINTENANCE", "OUT_OF_SERVICE", "DISABLED")
BATCH_STATUSES = ("OPEN", "STARTED", "COMPLETED", "ABORTED")
QC_RESULTS = ("PASS", "FAIL", "REWORK_REQUIRED", "MANAGER_REVIEW")
INCIDENT_KINDS = (
    "MISSING",
    "DAMAGED",
    "WRONG_TAG",
    "WRONG_CUSTOMER",
    "PROCESSING_DAMAGE",
    "STAIN_REMAINS",
    "WRONG_SERVICE",
    "COUNT_DISCREPANCY",
    "MACHINE_FAILURE",
)


class LaundrySortingCategory(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_sorting_categories"
    __table_args__ = (tenant_unique("code", name="uq_laundry_sorting_categories_code"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    workflow_code: Mapped[str] = mapped_column(String(40), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LaundryMachine(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_machines"
    __table_args__ = (
        tenant_unique("code", name="uq_laundry_machines_code"),
        CheckConstraint("capacity IS NULL OR capacity >= 0", name="ck_laundry_machines_capacity"),
        CheckConstraint("version >= 1", name="ck_laundry_machines_version"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    machine_type: Mapped[str] = mapped_column(String(20))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    plant_store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capacity_unit: Mapped[str] = mapped_column(String(16), default="G")
    status: Mapped[str] = mapped_column(String(20), default="AVAILABLE", index=True)
    maintenance_note: Mapped[str] = mapped_column(String(500), default="")
    version: Mapped[int] = mapped_column(Integer, default=1)


class LaundryBatch(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_batches"
    __table_args__ = (
        tenant_unique("code", name="uq_laundry_batches_code"),
        tenant_unique("idempotency_key", name="uq_laundry_batches_key"),
        CheckConstraint("version >= 1", name="ck_laundry_batches_version"),
        CheckConstraint("load_weight IS NULL OR load_weight >= 0", name="ck_laundry_batches_load"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(24))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    store_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), index=True)
    workflow_code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    machine_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_machines.id"), nullable=True
    )
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    load_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaundryBatchItem(TenantScoped, Base):
    __tablename__ = "laundry_batch_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_batches.id"), index=True)
    garment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), nullable=True, index=True
    )
    bag_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_bags.id"), nullable=True)
    removed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryMachineCycle(TenantScoped, Base):
    __tablename__ = "laundry_machine_cycles"
    __table_args__ = (
        tenant_unique("idempotency_key", name="uq_laundry_machine_cycles_key"),
        CheckConstraint("load_weight IS NULL OR load_weight > 0", name="ck_laundry_machine_cycles_load"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    machine_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_machines.id"), index=True)
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_batches.id"), nullable=True, index=True
    )
    cycle_code: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(16), default="RUNNING", index=True)
    load_weight: Mapped[int | None] = mapped_column(Integer, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    operator_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    issue: Mapped[str] = mapped_column(String(500), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaundryStageEvent(TenantScoped, Base):
    __tablename__ = "laundry_stage_events"
    __table_args__ = (tenant_unique("idempotency_key", name="uq_laundry_stage_events_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    from_stage: Mapped[str] = mapped_column(String(32))
    to_stage: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(500), default="")
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    store_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("stores.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryInspection(TenantScoped, Base):
    __tablename__ = "laundry_inspections"
    __table_args__ = (tenant_unique("idempotency_key", name="uq_laundry_inspections_key"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    result: Mapped[str] = mapped_column(String(20))
    checklist: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500), default="")
    idempotency_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LaundryReworkTask(TenantScoped, Base):
    __tablename__ = "laundry_rework_tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    garment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), index=True)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    inspection_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_inspections.id"))
    reason: Mapped[str] = mapped_column(String(500))
    required_stage: Mapped[str] = mapped_column(String(32))
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaundryIncident(TenantScoped, TimestampMixin, Base):
    __tablename__ = "laundry_incidents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    garment_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), nullable=True, index=True
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("laundry_batches.id"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32))
    stage: Mapped[str] = mapped_column(String(32), default="")
    location: Mapped[str] = mapped_column(String(80), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="OPEN", index=True)
    blocks_ready: Mapped[bool] = mapped_column(Boolean, default=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str] = mapped_column(String(500), default="")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LaundryPackingScan(TenantScoped, Base):
    __tablename__ = "laundry_packing_scans"
    __table_args__ = (
        tenant_unique("idempotency_key", name="uq_laundry_packing_scans_key"),
        tenant_unique("garment_id", "rework_count", name="uq_laundry_packing_scans_generation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_orders.id"), index=True)
    garment_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("laundry_garments.id"), index=True)
    bag_code: Mapped[str] = mapped_column(String(40), default="")
    rework_count: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[str] = mapped_column(String(80))
    actor_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
