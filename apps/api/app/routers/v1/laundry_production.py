"""Laundry production routes. The register and Business Pro call the same engine."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, authorize_any
from app.core.permissions import Permission
from app.schemas.laundry_production import (
    BatchActionIn,
    BatchIn,
    BatchItemIn,
    BatchOut,
    BoardOut,
    CategoryIn,
    CycleCloseIn,
    CycleIn,
    CycleOut,
    GarmentCard,
    HistoryOut,
    IncidentCloseIn,
    IncidentIn,
    IncidentOut,
    InspectionIn,
    InspectionOut,
    MachineIn,
    MachineOut,
    MachinePatch,
    NamedRow,
    PackingCompleteIn,
    PackingScanIn,
    ReworkCloseIn,
    ScanIn,
    ScanOut,
    ShiftOut,
    TransitionIn,
    WorkflowIn,
)
from app.services import laundry_production

router = APIRouter()
_POS = ("portal", "pos")
Db = Annotated[Session, Depends(get_db)]

_READ = authorize_any(
    Permission.LAUNDRY_PRODUCTION_VIEW,
    Permission.LAUNDRY_ORDERS_VIEW,
    Permission.LAUNDRY_GARMENTS_VIEW,
    Permission.LAUNDRY_PRODUCTION_SORT,
    Permission.LAUNDRY_PRODUCTION_PROCESS,
    Permission.LAUNDRY_PRODUCTION_FINISH,
    Permission.LAUNDRY_QUALITY_INSPECT,
    Permission.LAUNDRY_PACKING,
    Permission.LAUNDRY_PRODUCTION_OVERRIDE,
    Permission.LAUNDRY_BATCHES_MANAGE,
    Permission.LAUNDRY_MACHINES_CONFIGURE,
    Permission.LAUNDRY_MACHINES_OPERATE,
    Permission.LAUNDRY_INCIDENTS_REPORT,
    Permission.LAUNDRY_INCIDENTS_RESOLVE,
    Permission.LAUNDRY_CONFIGURE,
    scopes=_POS,
)
_MOVE = authorize_any(
    Permission.LAUNDRY_PRODUCTION_SORT,
    Permission.LAUNDRY_PRODUCTION_PROCESS,
    Permission.LAUNDRY_PRODUCTION_FINISH,
    Permission.LAUNDRY_QUALITY_INSPECT,
    Permission.LAUNDRY_PACKING,
    Permission.LAUNDRY_PRODUCTION_OVERRIDE,
    scopes=_POS,
)
Read = Annotated[Principal, Depends(_READ)]
Move = Annotated[Principal, Depends(_MOVE)]
Configure = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_CONFIGURE, scopes=_POS))]
Batches = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_BATCHES_MANAGE, scopes=_POS))]
Machines = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_MACHINES_CONFIGURE, scopes=_POS))]
Operate = Annotated[
    Principal,
    Depends(authorize_any(Permission.LAUNDRY_MACHINES_OPERATE, Permission.LAUNDRY_MACHINES_CONFIGURE, scopes=_POS)),
]
Inspect = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_QUALITY_INSPECT, scopes=_POS))]
Report = Annotated[
    Principal,
    Depends(authorize_any(Permission.LAUNDRY_INCIDENTS_REPORT, Permission.LAUNDRY_INCIDENTS_RESOLVE, scopes=_POS)),
]
Resolve = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_INCIDENTS_RESOLVE, scopes=_POS))]
Pack = Annotated[Principal, Depends(authorize(Permission.LAUNDRY_PACKING, scopes=_POS))]


def _actor(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


def _phone(principal: Principal) -> bool:
    return Permission.CUSTOMERS_MANAGE.value in principal.permissions


@router.get("/production/board", response_model=BoardOut)
def board(db: Db, principal: Read, store_id: uuid.UUID | None = None) -> dict:
    if principal.store_id is not None:
        store_id = principal.store_id
    result = laundry_production.board(db, store_id, include_phone=_phone(principal))
    db.commit()
    return result


@router.get("/production/shift", response_model=ShiftOut)
def shift(db: Db, principal: Read) -> dict:
    return laundry_production.shift_summary(db, _actor(principal))


@router.post("/production/scan", response_model=ScanOut)
def scan(payload: ScanIn, db: Db, principal: Read) -> dict:
    result = laundry_production.scan(
        db,
        payload.code,
        actor_store=principal.store_id,
        store_id=payload.store_id,
        permissions=principal.permissions,
        include_phone=_phone(principal),
        device_id=principal.device.id if principal.device is not None else None,
    )
    db.commit()
    return result


@router.get("/production/garments/{garment_id}", response_model=HistoryOut)
def garment(garment_id: uuid.UUID, db: Db, principal: Read) -> dict:
    return laundry_production.history(
        db, garment_id, permissions=principal.permissions, include_phone=_phone(principal)
    )


@router.post("/production/garments/{garment_id}/transition", response_model=GarmentCard)
def move(garment_id: uuid.UUID, payload: TransitionIn, db: Db, principal: Move) -> dict:
    garment = laundry_production.transition(
        db,
        garment_id,
        payload,
        actor_id=_actor(principal),
        actor_store=principal.store_id,
        permissions=principal.permissions,
    )
    db.commit()
    return laundry_production.present_garment(db, garment, include_phone=_phone(principal))


@router.get("/production/workflows", response_model=list[NamedRow])
def workflows(db: Db, principal: Read) -> list[dict]:
    rows = laundry_production.list_workflows(db)
    db.commit()
    return [
        {"id": row.id, "code": row.code, "name": row.name, "stages": list(row.stages), "is_active": row.is_active}
        for row in rows
    ]


@router.put("/production/workflows/{code}", response_model=NamedRow)
def save_workflow(code: str, payload: WorkflowIn, db: Db, principal: Configure) -> dict:
    row = laundry_production.save_workflow(db, code.strip().upper(), payload, actor_id=_actor(principal))
    db.commit()
    return {"id": row.id, "code": row.code, "name": row.name, "stages": list(row.stages), "is_active": row.is_active}


@router.get("/production/categories", response_model=list[NamedRow])
def categories(db: Db, principal: Read) -> list[dict]:
    rows = laundry_production.list_categories(db)
    db.commit()
    return [
        {
            "id": row.id,
            "code": row.code,
            "name": row.name,
            "workflow_code": row.workflow_code,
            "is_active": row.is_active,
        }
        for row in rows
    ]


@router.post("/production/categories", response_model=NamedRow, status_code=201)
def add_category(payload: CategoryIn, db: Db, principal: Configure) -> dict:
    row = laundry_production.add_category(db, payload)
    db.commit()
    return {
        "id": row.id,
        "code": row.code,
        "name": row.name,
        "workflow_code": row.workflow_code,
        "is_active": row.is_active,
    }


@router.get("/production/batches", response_model=list[BatchOut])
def batches(db: Db, principal: Read, store_id: uuid.UUID | None = None) -> list[dict]:
    if principal.store_id is not None:
        store_id = principal.store_id
    return laundry_production.list_batches(db, store_id)


@router.post("/production/batches", response_model=BatchOut, status_code=201)
def create_batch(payload: BatchIn, db: Db, principal: Batches) -> dict:
    batch = laundry_production.create_batch(db, payload, actor_id=_actor(principal), actor_store=principal.store_id)
    db.commit()
    return _batch(db, batch.id)


def _batch(db: Session, batch_id: uuid.UUID) -> dict:
    rows = laundry_production.list_batches(db, None)
    found = next(item for item in rows if item["id"] == batch_id)
    return found


@router.post("/production/batches/{batch_id}/items", response_model=BatchOut)
def add_item(batch_id: uuid.UUID, payload: BatchItemIn, db: Db, principal: Batches) -> dict:
    laundry_production.add_batch_item(db, batch_id, payload, actor_store=principal.store_id)
    db.commit()
    return _batch(db, batch_id)


@router.post("/production/batches/{batch_id}/items/{item_id}/remove", response_model=BatchOut)
def remove_item(batch_id: uuid.UUID, item_id: uuid.UUID, payload: BatchActionIn, db: Db, principal: Batches) -> dict:
    laundry_production.remove_batch_item(db, batch_id, item_id, version=payload.version, actor_store=principal.store_id)
    db.commit()
    return _batch(db, batch_id)


@router.post("/production/batches/{batch_id}/start", response_model=BatchOut)
def start_batch(batch_id: uuid.UUID, payload: BatchActionIn, db: Db, principal: Batches) -> dict:
    laundry_production.start_batch(db, batch_id, version=payload.version, actor_store=principal.store_id)
    db.commit()
    return _batch(db, batch_id)


@router.post("/production/batches/{batch_id}/complete", response_model=BatchOut)
def complete_batch(batch_id: uuid.UUID, payload: BatchActionIn, db: Db, principal: Batches) -> dict:
    laundry_production.complete_batch(db, batch_id, version=payload.version, actor_store=principal.store_id)
    db.commit()
    return _batch(db, batch_id)


@router.post("/production/batches/{batch_id}/abort", response_model=BatchOut)
def abort_batch(batch_id: uuid.UUID, payload: BatchActionIn, db: Db, principal: Batches) -> dict:
    laundry_production.abort_batch(
        db,
        batch_id,
        version=payload.version,
        reason=payload.reason,
        actor_store=principal.store_id,
        actor_id=_actor(principal),
    )
    db.commit()
    return _batch(db, batch_id)


@router.post("/production/batches/{batch_id}/machine", response_model=BatchOut)
def reassign(batch_id: uuid.UUID, payload: MachinePatch, db: Db, principal: Operate, machine_id: uuid.UUID) -> dict:
    laundry_production.reassign_batch_machine(
        db, batch_id, machine_id, version=payload.version, actor_store=principal.store_id
    )
    db.commit()
    return _batch(db, batch_id)


@router.get("/production/machines", response_model=list[MachineOut])
def machines(db: Db, principal: Operate, store_id: uuid.UUID | None = None) -> list:
    if principal.store_id is not None:
        store_id = principal.store_id
    return laundry_production.list_machines(db, store_id)


@router.post("/production/machines", response_model=MachineOut, status_code=201)
def create_machine(payload: MachineIn, db: Db, principal: Machines) -> object:
    row = laundry_production.register_machine(db, payload, actor_id=_actor(principal), actor_store=principal.store_id)
    db.commit()
    return row


@router.patch("/production/machines/{machine_id}", response_model=MachineOut)
def patch_machine(machine_id: uuid.UUID, payload: MachinePatch, db: Db, principal: Machines) -> object:
    row = laundry_production.update_machine(
        db, machine_id, payload, actor_id=_actor(principal), actor_store=principal.store_id
    )
    db.commit()
    return row


@router.post("/production/machines/{machine_id}/cycles", response_model=CycleOut, status_code=201)
def start_cycle(machine_id: uuid.UUID, payload: CycleIn, db: Db, principal: Operate) -> object:
    row = laundry_production.start_cycle(
        db, machine_id, payload, actor_id=_actor(principal), actor_store=principal.store_id
    )
    db.commit()
    return row


@router.post("/production/cycles/{cycle_id}/complete", response_model=CycleOut)
def complete_cycle(cycle_id: uuid.UUID, db: Db, principal: Operate) -> object:
    row = laundry_production.complete_cycle(db, cycle_id, actor_store=principal.store_id)
    db.commit()
    return row


@router.post("/production/cycles/{cycle_id}/fault", response_model=CycleOut)
def fault_cycle(cycle_id: uuid.UUID, payload: CycleCloseIn, db: Db, principal: Operate) -> object:
    row = laundry_production.fault_cycle(
        db, cycle_id, reason=payload.reason, actor_id=_actor(principal), actor_store=principal.store_id
    )
    db.commit()
    return row


@router.post("/production/inspections", response_model=InspectionOut, status_code=201)
def inspect(payload: InspectionIn, db: Db, principal: Inspect) -> object:
    row = laundry_production.inspect(db, payload, actor_id=_actor(principal), actor_store=principal.store_id)
    db.commit()
    return row


@router.post("/production/rework/{task_id}/complete")
def close_rework(task_id: uuid.UUID, payload: ReworkCloseIn, db: Db, principal: Inspect) -> dict:
    row = laundry_production.complete_rework(db, task_id, note=payload.note, actor_id=_actor(principal))
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.get("/production/incidents", response_model=list[IncidentOut])
def incidents(db: Db, principal: Report, store_id: uuid.UUID | None = None) -> list:
    if principal.store_id is not None:
        store_id = principal.store_id
    return laundry_production.list_incidents(db, store_id)


@router.post("/production/incidents", response_model=IncidentOut, status_code=201)
def open_incident(payload: IncidentIn, db: Db, principal: Report) -> object:
    row = laundry_production.report_incident(db, payload, actor_id=_actor(principal), actor_store=principal.store_id)
    db.commit()
    return row


@router.post("/production/incidents/{incident_id}/resolve", response_model=IncidentOut)
def close_incident(incident_id: uuid.UUID, payload: IncidentCloseIn, db: Db, principal: Resolve) -> object:
    row = laundry_production.resolve_incident(
        db,
        incident_id,
        status=payload.status,
        resolution=payload.resolution,
        actor_id=_actor(principal),
        actor_store=principal.store_id,
    )
    db.commit()
    return row


@router.post("/production/packing/scans", status_code=201)
def pack(payload: PackingScanIn, db: Db, principal: Pack) -> dict:
    row = laundry_production.pack_scan(db, payload, actor_id=_actor(principal), actor_store=principal.store_id)
    db.commit()
    return {"id": str(row.id), "garment_id": str(row.garment_id), "bag_code": row.bag_code}


@router.post("/production/orders/{order_id}/packing/complete", response_model=GarmentCard)
def finish_packing(order_id: uuid.UUID, payload: PackingCompleteIn, db: Db, principal: Pack) -> dict:
    order = laundry_production.complete_packing(
        db,
        order_id,
        idempotency_key=payload.idempotency_key,
        actor_id=_actor(principal),
        actor_store=principal.store_id,
        permissions=principal.permissions,
    )
    db.commit()
    from sqlalchemy import select

    from app.models.laundry_order import LaundryGarment

    row = db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)).first()
    if row is None:
        raise RuntimeError("packed order has no garment")
    return laundry_production.present_garment(db, row, include_phone=_phone(principal))
