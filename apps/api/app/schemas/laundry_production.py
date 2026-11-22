"""Laundry production requests. The server decides the next stage."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")


class ScanIn(ApiModel):
    code: str = Field(min_length=3, max_length=40)
    store_id: uuid.UUID | None = None


class TransitionIn(ApiModel):
    target: str = Field(min_length=3, max_length=32)
    version: int = Field(ge=1)
    idempotency_key: str = Field(min_length=8, max_length=80)
    reason: str = ""
    workflow_code: str = ""
    sorting_category: str = ""
    station: str = ""
    location: str = ""


class BatchIn(ApiModel):
    store_id: uuid.UUID
    workflow_code: str = Field(min_length=2, max_length=40)
    idempotency_key: str = Field(min_length=8, max_length=80)


class BatchItemIn(ApiModel):
    garment_id: uuid.UUID | None = None
    bag_id: uuid.UUID | None = None
    version: int = Field(ge=1)


class BatchActionIn(ApiModel):
    version: int = Field(ge=1)
    reason: str = ""


class MachineIn(ApiModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    machine_type: str
    store_id: uuid.UUID
    plant_store_id: uuid.UUID | None = None
    capacity: int | None = Field(default=None, ge=0)
    capacity_unit: str = "G"


class MachinePatch(ApiModel):
    name: str = ""
    status: str = ""
    maintenance_note: str = ""
    capacity: int | None = None
    version: int = Field(ge=1)


class CycleIn(ApiModel):
    batch_id: uuid.UUID | None = None
    cycle_code: str = Field(min_length=1, max_length=40)
    load_weight: int | None = Field(default=None, ge=1)
    idempotency_key: str = Field(min_length=8, max_length=80)
    expected_at: datetime | None = None


class CycleCloseIn(ApiModel):
    reason: str = ""
    idempotency_key: str = Field(min_length=8, max_length=80)


class InspectionIn(ApiModel):
    garment_id: uuid.UUID
    version: int = Field(ge=1)
    result: str
    checklist: dict[str, bool]
    reason: str = ""
    required_stage: str = ""
    idempotency_key: str = Field(min_length=8, max_length=80)


class ReworkCloseIn(ApiModel):
    note: str = ""


class IncidentIn(ApiModel):
    order_id: uuid.UUID
    garment_id: uuid.UUID | None = None
    batch_id: uuid.UUID | None = None
    kind: str
    description: str = Field(min_length=3, max_length=2000)
    location: str = ""
    blocks_ready: bool = True


class IncidentCloseIn(ApiModel):
    status: str
    resolution: str = Field(min_length=3, max_length=500)


class PackingScanIn(ApiModel):
    order_id: uuid.UUID
    garment_id: uuid.UUID
    bag_code: str = ""
    idempotency_key: str = Field(min_length=8, max_length=80)
    version: int = Field(ge=1)


class PackingCompleteIn(ApiModel):
    idempotency_key: str = Field(min_length=8, max_length=80)


class WorkflowIn(ApiModel):
    name: str = Field(min_length=1, max_length=120)
    stages: list[str] = Field(min_length=3)
    is_active: bool = True


class CategoryIn(ApiModel):
    code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=1, max_length=80)
    workflow_code: str = ""


class GarmentCard(ApiModel):
    id: uuid.UUID
    order_id: uuid.UUID
    order_code: str
    store_id: uuid.UUID
    customer_name: str
    customer_phone: str = ""
    description: str
    stage: str
    workflow_code: str
    service_name: str
    colour: str
    fabric: str
    brand: str
    size: str
    condition: str
    instructions: str
    tag_code: str
    version: int
    hold: bool
    qc_result: str
    rework_count: int
    sorting_category: str
    station: str
    location: str
    batch_id: uuid.UUID | None
    promised_at: datetime | None
    stage_entered_at: datetime | None
    total_cents: int
    tax_cents: int
    amount_paid_cents: int
    balance_due_cents: int
    operational_status: str


class ScanOut(ApiModel):
    result: str
    message: str
    allowed_targets: list[str]
    garment: GarmentCard | None = None


class BoardOut(ApiModel):
    received_today: int
    awaiting_sorting: int
    processing: int
    active_batches: int
    active_cycles: int
    qc_pending: int
    rework_pending: int
    packing_pending: int
    ready_orders: int
    overdue: int
    open_incidents: int
    garments: list[GarmentCard]


class ShiftOut(ApiModel):
    transitions: int
    inspections: int
    packed: int
    incidents: int


class NamedRow(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    workflow_code: str = ""
    is_active: bool = True
    stages: list[str] = []


class MachineOut(ApiModel):
    id: uuid.UUID
    code: str
    name: str
    machine_type: str
    store_id: uuid.UUID
    capacity: int | None
    capacity_unit: str
    status: str
    maintenance_note: str
    version: int


class BatchOut(ApiModel):
    id: uuid.UUID
    code: str
    store_id: uuid.UUID
    workflow_code: str
    status: str
    machine_id: uuid.UUID | None
    load_weight: int | None
    version: int
    item_count: int


class CycleOut(ApiModel):
    id: uuid.UUID
    machine_id: uuid.UUID
    batch_id: uuid.UUID | None
    cycle_code: str
    status: str
    load_weight: int | None
    issue: str


class InspectionOut(ApiModel):
    id: uuid.UUID
    garment_id: uuid.UUID
    result: str
    reason: str
    checklist: dict[str, bool]
    created_at: datetime


class IncidentOut(ApiModel):
    id: uuid.UUID
    order_id: uuid.UUID
    garment_id: uuid.UUID | None
    kind: str
    status: str
    blocks_ready: bool
    description: str
    resolution: str
    stage: str


class StageEventOut(ApiModel):
    from_stage: str
    to_stage: str
    reason: str
    created_at: datetime


class ReworkOut(ApiModel):
    id: uuid.UUID
    reason: str
    required_stage: str
    status: str


class HistoryOut(ApiModel):
    garment: GarmentCard
    stages: list[str]
    next_stage: str
    allowed_targets: list[str]
    events: list[StageEventOut]
    inspections: list[InspectionOut]
    incidents: list[IncidentOut]
    photo_ids: list[uuid.UUID]
    open_rework: ReworkOut | None = None
