"""Laundry production floor. Stage changes, batches, and machines stay on the server.

Offline clients must not invent a completed stage. Machine capacity, batch exclusivity, and
conflicting moves need the current database row.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, time

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.customer import Customer
from app.models.laundry import LaundryService, LaundryWorkflowTemplate
from app.models.laundry_order import (
    LaundryBag,
    LaundryDeposit,
    LaundryGarment,
    LaundryOrder,
    LaundryOrderEvent,
    LaundryPhoto,
    LaundryTag,
    LaundryTagEvent,
)
from app.models.laundry_production import (
    INCIDENT_KINDS,
    MACHINE_STATUSES,
    MACHINE_TYPES,
    QC_RESULTS,
    LaundryBatch,
    LaundryBatchItem,
    LaundryIncident,
    LaundryInspection,
    LaundryMachine,
    LaundryMachineCycle,
    LaundryPackingScan,
    LaundryReworkTask,
    LaundrySortingCategory,
    LaundryStageEvent,
)
from app.schemas.laundry_production import (
    BatchIn,
    BatchItemIn,
    CategoryIn,
    CycleIn,
    IncidentIn,
    InspectionIn,
    MachineIn,
    MachinePatch,
    PackingScanIn,
    TransitionIn,
    WorkflowIn,
)
from app.services import audit
from app.services.laundry_catalog import workflow_stages
from app.services.laundry_orders import get_order

_STAGE_PERMISSION = {
    "SORTING": Permission.LAUNDRY_PRODUCTION_SORT.value,
    "WASHING": Permission.LAUNDRY_PRODUCTION_PROCESS.value,
    "DRYING": Permission.LAUNDRY_PRODUCTION_PROCESS.value,
    "PRE_TREATMENT": Permission.LAUNDRY_PRODUCTION_PROCESS.value,
    "DRY_CLEANING": Permission.LAUNDRY_PRODUCTION_PROCESS.value,
    "FOLDING": Permission.LAUNDRY_PRODUCTION_FINISH.value,
    "FINISHING": Permission.LAUNDRY_PRODUCTION_FINISH.value,
    "IRONING": Permission.LAUNDRY_PRODUCTION_FINISH.value,
    "QUALITY_CHECK": Permission.LAUNDRY_QUALITY_INSPECT.value,
    "PACKING": Permission.LAUNDRY_PACKING.value,
    "READY_FOR_COLLECTION": Permission.LAUNDRY_PACKING.value,
}
_CHECKLIST = (
    "cleaning",
    "stain",
    "finishing",
    "ironing",
    "fabric",
    "buttons",
    "zippers",
    "tag",
    "order",
    "instructions",
)
_MACHINE_WORKFLOWS = {
    "WASHER": {"WASH_FOLD", "WASH_IRON"},
    "DRYER": {"WASH_FOLD", "WASH_IRON"},
    "DRY_CLEANING": {"DRY_CLEAN"},
    "PRESS": {"PRESS", "WASH_IRON", "DRY_CLEAN"},
    "FOLDER": {"WASH_FOLD"},
}
_PROCESSING = {"SORTING", "WASHING", "DRYING", "FOLDING", "PRE_TREATMENT", "DRY_CLEANING", "FINISHING", "IRONING"}
_KNOWN_STAGES = {
    "RECEIVED",
    "TAGGED",
    "SORTING",
    "WASHING",
    "DRYING",
    "FOLDING",
    "PRE_TREATMENT",
    "DRY_CLEANING",
    "FINISHING",
    "IRONING",
    "QUALITY_CHECK",
    "PACKING",
    "READY_FOR_COLLECTION",
}
_CLOSED = {"READY_FOR_COLLECTION", "READY", "COLLECTED", "CANCELLED"}


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _token(stage: str) -> str:
    return "READY_FOR_COLLECTION" if stage == "READY" else stage


def _stored(token: str) -> str:
    return "READY" if token == "READY_FOR_COLLECTION" else token


def ensure_floor(db: Session) -> None:
    """Adds the built-in sort labels and wash-and-iron template when this tenant has none."""
    if db.scalar(select(LaundrySortingCategory.id).limit(1)) is None:
        for code, name in (("mixed", "Mixed"), ("light", "Light"), ("dark", "Dark")):
            db.add(LaundrySortingCategory(code=code, name=name, workflow_code="", is_active=True))
    if db.scalar(select(LaundryWorkflowTemplate.id).where(LaundryWorkflowTemplate.code == "WASH_IRON")) is None:
        stages = workflow_stages("WASH_IRON")
        if stages:
            db.add(LaundryWorkflowTemplate(code="WASH_IRON", name="Wash and iron", stages=stages, is_active=True))
    db.flush()


def _chain(db: Session, code: str) -> list[str]:
    row = db.scalar(
        select(LaundryWorkflowTemplate).where(
            LaundryWorkflowTemplate.code == code, LaundryWorkflowTemplate.is_active.is_(True)
        )
    )
    if row is not None and isinstance(row.stages, list) and row.stages:
        return [str(item) for item in row.stages]
    return workflow_stages(code)


def _next(chain: list[str], stage: str) -> str:
    token = _token(stage)
    if token not in chain:
        return ""
    index = chain.index(token)
    if index + 1 >= len(chain):
        return ""
    return chain[index + 1]


def _branch(actor_store: uuid.UUID | None, store_id: uuid.UUID | None) -> None:
    if actor_store is not None and store_id is not None and actor_store != store_id:
        raise ApiError(403, "wrong_branch", "That work belongs to another branch.")


def _claim_garment(db: Session, garment: LaundryGarment, expected: int) -> None:
    result = db.execute(
        update(LaundryGarment)
        .where(LaundryGarment.id == garment.id, LaundryGarment.version == expected)
        .values(version=expected + 1)
    )
    if result.rowcount != 1:
        raise ApiError(409, "garment_conflict", "This garment was updated by someone else.")
    garment.version = expected + 1


def _claim_batch(db: Session, batch: LaundryBatch, expected: int) -> None:
    result = db.execute(
        update(LaundryBatch)
        .where(LaundryBatch.id == batch.id, LaundryBatch.version == expected)
        .values(version=expected + 1)
    )
    if result.rowcount != 1:
        raise ApiError(409, "batch_conflict", "This batch was updated by someone else.")
    batch.version = expected + 1


def _garment(db: Session, garment_id: uuid.UUID) -> LaundryGarment:
    garment = db.get(LaundryGarment, garment_id)
    if garment is None:
        raise ApiError(404, "not_found", "That garment is not in this business.")
    return garment


def _open_order(order: LaundryOrder) -> None:
    if order.operational_status == "CANCELLED":
        raise ApiError(409, "order_closed", "A cancelled order cannot move through production.")


def _blocking(db: Session, order_id: uuid.UUID) -> bool:
    found = db.scalar(
        select(LaundryIncident.id).where(
            LaundryIncident.order_id == order_id,
            LaundryIncident.blocks_ready.is_(True),
            LaundryIncident.status.in_(("OPEN", "INVESTIGATING")),
        )
    )
    return found is not None


def _refresh_order(db: Session, order: LaundryOrder, actor_id: uuid.UUID | None) -> None:
    if order.operational_status in {"CANCELLED", "COLLECTED"}:
        return
    garments = list(db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)))
    if not garments:
        return
    ready = all(item.stage == "READY" and not item.hold for item in garments) and not _blocking(db, order.id)
    if ready:
        new_status = "READY_FOR_COLLECTION"
    elif any(item.stage not in {"RECEIVED", "TAGGED"} or item.hold for item in garments):
        new_status = "IN_PRODUCTION"
    else:
        return
    if order.operational_status == new_status:
        return
    previous = order.operational_status
    order.operational_status = new_status
    order.version += 1
    db.add(
        LaundryOrderEvent(
            order_id=order.id,
            kind="production_stage",
            from_status=previous,
            to_status=new_status,
            reason="",
            actor_id=actor_id,
        )
    )


def _tag_code(db: Session, garment_id: uuid.UUID) -> str:
    tag = db.scalar(
        select(LaundryTag).where(LaundryTag.garment_id == garment_id, LaundryTag.status == "active").limit(1)
    )
    return tag.code if tag is not None else ""


def present_garment(db: Session, garment: LaundryGarment, *, include_phone: bool) -> dict:
    order = get_order(db, garment.order_id)
    customer = db.get(Customer, order.customer_id)
    service = db.get(LaundryService, garment.service_id)
    return {
        "id": garment.id,
        "order_id": order.id,
        "order_code": order.code,
        "store_id": order.intake_store_id,
        "customer_name": customer.name if customer is not None else "",
        "customer_phone": customer.phone or "" if include_phone and customer is not None and customer.phone else "",
        "description": garment.description,
        "stage": garment.stage,
        "workflow_code": garment.workflow_code,
        "service_name": service.name if service is not None else "",
        "colour": garment.colour,
        "fabric": garment.fabric,
        "brand": garment.brand,
        "size": garment.size,
        "condition": garment.condition,
        "instructions": garment.instructions,
        "tag_code": _tag_code(db, garment.id),
        "version": garment.version,
        "hold": garment.hold,
        "qc_result": garment.qc_result,
        "rework_count": garment.rework_count,
        "sorting_category": garment.sorting_category,
        "station": garment.station,
        "location": garment.location_label,
        "batch_id": garment.current_batch_id,
        "promised_at": order.promised_at,
        "stage_entered_at": garment.stage_entered_at,
        "total_cents": order.total_cents,
        "tax_cents": order.tax_cents,
        "amount_paid_cents": order.amount_paid_cents,
        "balance_due_cents": order.balance_due_cents,
        "operational_status": order.operational_status,
    }


def allowed_targets(db: Session, garment: LaundryGarment, permissions: frozenset[str]) -> list[str]:
    chain = _chain(db, garment.workflow_code)
    nxt = _next(chain, garment.stage)
    if not nxt:
        return []
    if garment.hold and nxt in {"PACKING", "READY_FOR_COLLECTION"}:
        return []
    allowed = []
    needed = _STAGE_PERMISSION.get(nxt)
    if needed and (needed in permissions or Permission.LAUNDRY_PRODUCTION_OVERRIDE.value in permissions):
        allowed.append(nxt)
    return allowed


def _normalize(target: str) -> str:
    cleaned = target.strip().upper()
    if cleaned == "READY":
        return "READY_FOR_COLLECTION"
    return cleaned


def scan(
    db: Session,
    code: str,
    *,
    actor_store: uuid.UUID | None,
    store_id: uuid.UUID | None,
    permissions: frozenset[str],
    include_phone: bool,
    device_id: uuid.UUID | None,
) -> dict:
    tag = db.scalar(select(LaundryTag).where(LaundryTag.code == code.strip()))
    if tag is None:
        raise ApiError(404, "unknown_tag", "That tag is not in this business.")
    if tag.status == "replaced":
        raise ApiError(409, "replaced_tag", "That tag was replaced. Scan the new tag.")
    if tag.status != "active":
        raise ApiError(409, "inactive_tag", "That tag is not active.")
    branch = store_id or tag.store_id
    _branch(actor_store, branch)
    if actor_store is None and store_id is not None and store_id != tag.store_id:
        raise ApiError(403, "wrong_branch", "That tag belongs to another branch.")
    if tag.garment_id is None:
        return {
            "result": "bag_tag",
            "message": "That tag is on a bag. Scan a garment tag.",
            "allowed_targets": [],
            "garment": None,
        }
    garment = _garment(db, tag.garment_id)
    latest = db.scalar(
        select(LaundryTagEvent)
        .where(LaundryTagEvent.tag_id == tag.id, LaundryTagEvent.kind == "scan", LaundryTagEvent.note == garment.stage)
        .order_by(LaundryTagEvent.created_at.desc())
        .limit(1)
    )
    entered = garment.stage_entered_at
    if latest is not None and entered is not None and _aware(latest.created_at) < _aware(entered):
        latest = None
    if latest is None:
        db.add(
            LaundryTagEvent(
                tag_id=tag.id,
                order_id=tag.order_id,
                kind="scan",
                idempotency_key=f"scan:{tag.id}:{garment.stage}:{garment.version}",
                note=garment.stage,
                device_id=device_id,
            )
        )
        result, message = "valid", "Garment found. Choose the next action."
    else:
        result, message = "already_scanned", "This garment was already scanned at this stage."
    return {
        "result": result,
        "message": message,
        "allowed_targets": allowed_targets(db, garment, permissions),
        "garment": present_garment(db, garment, include_phone=include_phone),
    }


def history(db: Session, garment_id: uuid.UUID, *, permissions: frozenset[str], include_phone: bool) -> dict:
    garment = _garment(db, garment_id)
    events = list(
        db.scalars(
            select(LaundryStageEvent)
            .where(LaundryStageEvent.garment_id == garment.id)
            .order_by(LaundryStageEvent.created_at)
        )
    )
    inspections = list(db.scalars(select(LaundryInspection).where(LaundryInspection.garment_id == garment.id)))
    incidents = list(db.scalars(select(LaundryIncident).where(LaundryIncident.garment_id == garment.id)))
    photos = list(db.scalars(select(LaundryPhoto.id).where(LaundryPhoto.garment_id == garment.id)))
    chain = _chain(db, garment.workflow_code)
    open_rework = db.scalar(
        select(LaundryReworkTask)
        .where(LaundryReworkTask.garment_id == garment.id, LaundryReworkTask.status == "OPEN")
        .order_by(LaundryReworkTask.created_at.desc())
    )
    return {
        "garment": present_garment(db, garment, include_phone=include_phone),
        "stages": chain,
        "next_stage": _next(chain, garment.stage),
        "allowed_targets": allowed_targets(db, garment, permissions),
        "events": events,
        "inspections": inspections,
        "incidents": incidents,
        "photo_ids": photos,
        "open_rework": open_rework,
    }


def _apply_stage(
    db: Session,
    garment: LaundryGarment,
    order: LaundryOrder,
    target: str,
    *,
    actor_id: uuid.UUID | None,
    reason: str,
    key: str,
) -> None:
    previous = garment.stage
    garment.stage = _stored(target)
    garment.stage_entered_at = _now()
    db.add(
        LaundryStageEvent(
            garment_id=garment.id,
            order_id=order.id,
            from_stage=previous,
            to_stage=garment.stage,
            idempotency_key=key,
            reason=reason[:500],
            actor_id=actor_id,
            store_id=garment.location_store_id,
        )
    )
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.production.transition",
        target_entity="LaundryGarment",
        target_entity_id=garment.id,
        user_id=actor_id,
        reason_notes=reason or None,
        details={"from": previous, "to": garment.stage, "order_id": str(order.id), "key": key},
    )


def transition(
    db: Session,
    garment_id: uuid.UUID,
    payload: TransitionIn,
    *,
    actor_id: uuid.UUID | None,
    actor_store: uuid.UUID | None,
    permissions: frozenset[str],
) -> LaundryGarment:
    ensure_floor(db)
    garment = _garment(db, garment_id)
    order = get_order(db, garment.order_id)
    _open_order(order)
    _branch(actor_store, garment.location_store_id or order.intake_store_id)
    target = _normalize(payload.target)
    existing = db.scalar(select(LaundryStageEvent).where(LaundryStageEvent.idempotency_key == payload.idempotency_key))
    if existing is not None:
        if existing.garment_id != garment.id or existing.to_stage != _stored(target):
            raise ApiError(409, "idempotency_conflict", "That request was already used for a different move.")
        return garment
    workflow = garment.workflow_code
    if payload.workflow_code and garment.stage in {"RECEIVED", "TAGGED"}:
        workflow = payload.workflow_code.strip().upper()
    chain = _chain(db, workflow)
    if not chain or target not in chain:
        raise ApiError(422, "wrong_workflow", "That stage is not in this garment's workflow.")
    current = _token(garment.stage)
    if current not in chain:
        raise ApiError(422, "wrong_workflow", "This garment is not on a configured production stage.")
    jump = chain.index(target) - chain.index(current)
    override = Permission.LAUNDRY_PRODUCTION_OVERRIDE.value in permissions
    if jump == 0:
        raise ApiError(409, "already_there", "The garment is already at that stage.")
    if jump < 0:
        raise ApiError(422, "wrong_workflow", "Send the garment back through rework, not a forward move.")
    if jump != 1 and not (override and len(payload.reason.strip()) >= 3):
        raise ApiError(422, "wrong_workflow", "Only the next stage in the workflow is allowed.")
    needed = _STAGE_PERMISSION.get(target)
    if needed is None or (needed not in permissions and not override):
        raise ApiError(403, "forbidden", "You cannot move a garment to that stage.")
    if garment.hold and target in {"PACKING", "READY_FOR_COLLECTION"}:
        raise ApiError(422, "incident_hold", "An open incident is holding this garment.")
    if target in {"PACKING", "READY_FOR_COLLECTION"} and "QUALITY_CHECK" in chain and garment.qc_result != "PASS":
        raise ApiError(422, "qc_required", "A failed or missing inspection cannot go on to packing or ready.")
    if target == "READY_FOR_COLLECTION":
        if _blocking(db, order.id):
            raise ApiError(422, "incident_hold", "An open incident is holding this order.")
        packed = db.scalar(
            select(LaundryPackingScan.id).where(
                LaundryPackingScan.garment_id == garment.id,
                LaundryPackingScan.rework_count == garment.rework_count,
            )
        )
        if packed is None:
            raise ApiError(422, "not_packed", "Scan the garment into its packing bag first.")
    category_row = None
    if target == "SORTING":
        category = (payload.sorting_category or garment.sorting_category).strip().lower()
        if not category:
            raise ApiError(422, "category_required", "Choose a sorting category.")
        category_row = db.scalar(
            select(LaundrySortingCategory).where(
                LaundrySortingCategory.code == category, LaundrySortingCategory.is_active.is_(True)
            )
        )
        if category_row is None:
            raise ApiError(422, "unknown_category", "Choose a configured sorting category.")
        if category_row.workflow_code and category_row.workflow_code != workflow:
            raise ApiError(422, "category_conflict", "That category belongs to a different workflow.")
    _claim_garment(db, garment, payload.version)
    garment.workflow_code = workflow
    if category_row is not None:
        garment.sorting_category = category_row.code
    if payload.station.strip():
        garment.station = payload.station.strip()[:40]
    if payload.location.strip():
        garment.location_label = payload.location.strip()[:80]
    if actor_id is not None:
        garment.assigned_user_id = actor_id
    _apply_stage(
        db, garment, order, target, actor_id=actor_id, reason=payload.reason.strip(), key=payload.idempotency_key
    )
    _refresh_order(db, order, actor_id)
    return garment


def board(db: Session, store_id: uuid.UUID | None, *, include_phone: bool) -> dict:
    ensure_floor(db)
    garments = list(db.scalars(select(LaundryGarment)))
    if store_id is not None:
        garments = [item for item in garments if item.location_store_id == store_id]
    orders = list(db.scalars(select(LaundryOrder)))
    if store_id is not None:
        orders = [item for item in orders if item.intake_store_id == store_id]
    start = datetime.combine(_now().date(), time.min, tzinfo=UTC)
    batches = list(db.scalars(select(LaundryBatch).where(LaundryBatch.status.in_(("OPEN", "STARTED")))))
    cycles = list(db.scalars(select(LaundryMachineCycle).where(LaundryMachineCycle.status == "RUNNING")))
    incidents = int(
        db.scalar(
            select(func.count())
            .select_from(LaundryIncident)
            .where(LaundryIncident.status.in_(("OPEN", "INVESTIGATING")))
        )
        or 0
    )
    rework = int(
        db.scalar(select(func.count()).select_from(LaundryReworkTask).where(LaundryReworkTask.status == "OPEN")) or 0
    )
    cards = [present_garment(db, item, include_phone=include_phone) for item in garments[:100]]
    return {
        "received_today": sum(
            1 for item in orders if item.created_at >= start and item.operational_status != "CANCELLED"
        ),
        "awaiting_sorting": sum(1 for item in garments if item.stage == "TAGGED"),
        "processing": sum(1 for item in garments if item.stage in _PROCESSING),
        "active_batches": len(batches),
        "active_cycles": len(cycles),
        "qc_pending": sum(1 for item in garments if item.stage == "QUALITY_CHECK"),
        "rework_pending": rework,
        "packing_pending": sum(1 for item in garments if item.stage == "PACKING"),
        "ready_orders": sum(1 for item in orders if item.operational_status == "READY_FOR_COLLECTION"),
        "overdue": sum(
            1
            for item in orders
            if item.promised_at is not None and item.promised_at < _now() and item.operational_status not in _CLOSED
        ),
        "open_incidents": incidents,
        "garments": cards,
    }


def shift_summary(db: Session, actor_id: uuid.UUID | None) -> dict:
    start = datetime.combine(_now().date(), time.min, tzinfo=UTC)
    moves = select(func.count()).select_from(LaundryStageEvent).where(LaundryStageEvent.created_at >= start)
    checks = select(func.count()).select_from(LaundryInspection).where(LaundryInspection.created_at >= start)
    packed = select(func.count()).select_from(LaundryPackingScan).where(LaundryPackingScan.created_at >= start)
    incidents = select(func.count()).select_from(LaundryIncident).where(LaundryIncident.created_at >= start)
    if actor_id is not None:
        moves = moves.where(LaundryStageEvent.actor_id == actor_id)
        checks = checks.where(LaundryInspection.actor_id == actor_id)
        packed = packed.where(LaundryPackingScan.actor_id == actor_id)
        incidents = incidents.where(LaundryIncident.actor_id == actor_id)
    return {
        "transitions": int(db.scalar(moves) or 0),
        "inspections": int(db.scalar(checks) or 0),
        "packed": int(db.scalar(packed) or 0),
        "incidents": int(db.scalar(incidents) or 0),
    }


def save_workflow(
    db: Session, code: str, payload: WorkflowIn, *, actor_id: uuid.UUID | None
) -> LaundryWorkflowTemplate:
    stages = [item.strip().upper() for item in payload.stages]
    if stages[0] != "RECEIVED" or stages[1] != "TAGGED" or stages[-1] != "READY_FOR_COLLECTION":
        raise ApiError(
            422, "invalid_workflow", "A workflow starts at received and tagged, and ends ready for collection."
        )
    if len(stages) != len(set(stages)) or any(item not in _KNOWN_STAGES for item in stages):
        raise ApiError(422, "invalid_workflow", "Use each known stage once.")
    row = db.scalar(select(LaundryWorkflowTemplate).where(LaundryWorkflowTemplate.code == code))
    if row is None:
        row = LaundryWorkflowTemplate(code=code, name=payload.name, stages=stages, is_active=payload.is_active)
        db.add(row)
    else:
        row.name = payload.name
        row.stages = stages
        row.is_active = payload.is_active
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.workflow",
        target_entity="LaundryWorkflowTemplate",
        target_entity_id=row.id,
        user_id=actor_id,
        details={"code": code, "stages": stages},
    )
    db.flush()
    return row


def add_category(db: Session, payload: CategoryIn) -> LaundrySortingCategory:
    code = payload.code.strip().lower()
    if db.scalar(select(LaundrySortingCategory.id).where(LaundrySortingCategory.code == code)) is not None:
        raise ApiError(409, "duplicate_category", "That sorting category already exists.")
    row = LaundrySortingCategory(
        code=code, name=payload.name.strip(), workflow_code=payload.workflow_code.strip().upper()
    )
    db.add(row)
    db.flush()
    return row


def list_categories(db: Session) -> list[LaundrySortingCategory]:
    ensure_floor(db)
    return list(db.scalars(select(LaundrySortingCategory).order_by(LaundrySortingCategory.name)))


def list_workflows(db: Session) -> list[LaundryWorkflowTemplate]:
    ensure_floor(db)
    return list(db.scalars(select(LaundryWorkflowTemplate).order_by(LaundryWorkflowTemplate.code)))


def _active_membership(db: Session, garment_id: uuid.UUID) -> LaundryBatchItem | None:
    return db.scalar(
        select(LaundryBatchItem)
        .join(LaundryBatch, LaundryBatch.id == LaundryBatchItem.batch_id)
        .where(
            LaundryBatchItem.garment_id == garment_id,
            LaundryBatchItem.removed_at.is_(None),
            LaundryBatch.status.in_(("OPEN", "STARTED")),
        )
    )


def create_batch(
    db: Session, payload: BatchIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryBatch:
    ensure_floor(db)
    _branch(actor_store, payload.store_id)
    if not _chain(db, payload.workflow_code):
        raise ApiError(422, "wrong_workflow", "Choose a configured workflow.")
    existing = db.scalar(select(LaundryBatch).where(LaundryBatch.idempotency_key == payload.idempotency_key))
    if existing is not None:
        return existing
    batch = LaundryBatch(
        code=f"LB-{uuid.uuid4().hex[:8].upper()}",
        idempotency_key=payload.idempotency_key,
        store_id=payload.store_id,
        workflow_code=payload.workflow_code.strip().upper(),
        status="OPEN",
        operator_id=actor_id,
    )
    db.add(batch)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.batch",
        target_entity="LaundryBatch",
        target_entity_id=batch.id,
        user_id=actor_id,
        details={"code": batch.code, "workflow": batch.workflow_code},
    )
    return batch


def _recompute_load(db: Session, batch: LaundryBatch) -> None:
    items = list(
        db.scalars(
            select(LaundryBatchItem).where(LaundryBatchItem.batch_id == batch.id, LaundryBatchItem.removed_at.is_(None))
        )
    )
    weights = []
    for item in items:
        if item.bag_id is None:
            continue
        bag = db.get(LaundryBag, item.bag_id)
        if bag is not None:
            weights.append(bag.net_weight)
    batch.load_weight = sum(weights) if weights else None


def add_batch_item(
    db: Session, batch_id: uuid.UUID, payload: BatchItemIn, *, actor_store: uuid.UUID | None
) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "That batch does not exist.")
    _branch(actor_store, batch.store_id)
    if batch.status != "OPEN":
        raise ApiError(409, "batch_closed", "Items can only be added before the batch starts.")
    if (payload.garment_id is None) == (payload.bag_id is None):
        raise ApiError(422, "item_required", "Add one garment or one bag.")
    if payload.garment_id is not None:
        garment = _garment(db, payload.garment_id)
        order = get_order(db, garment.order_id)
        _open_order(order)
        if garment.workflow_code != batch.workflow_code:
            raise ApiError(422, "wrong_workflow", "That garment uses a different workflow.")
        if garment.stage == "READY":
            raise ApiError(409, "already_ready", "A ready garment cannot join a batch.")
        current = _active_membership(db, garment.id)
        if current is not None:
            if current.batch_id == batch.id:
                return batch
            raise ApiError(409, "duplicate_batch", "That garment is already in an active batch.")
        _claim_batch(db, batch, payload.version)
        db.add(LaundryBatchItem(batch_id=batch.id, garment_id=garment.id))
        garment.current_batch_id = batch.id
    else:
        bag = db.get(LaundryBag, payload.bag_id)
        if bag is None:
            raise ApiError(404, "not_found", "That bag is not in this business.")
        service = db.get(LaundryService, bag.service_id)
        if service is None or service.workflow_code != batch.workflow_code:
            raise ApiError(422, "wrong_workflow", "That bag uses a different workflow.")
        _claim_batch(db, batch, payload.version)
        db.add(LaundryBatchItem(batch_id=batch.id, bag_id=bag.id))
    db.flush()
    _recompute_load(db, batch)
    return batch


def remove_batch_item(
    db: Session, batch_id: uuid.UUID, item_id: uuid.UUID, *, version: int, actor_store: uuid.UUID | None
) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    item = db.get(LaundryBatchItem, item_id)
    if batch is None or item is None or item.batch_id != batch.id:
        raise ApiError(404, "not_found", "That batch item does not exist.")
    _branch(actor_store, batch.store_id)
    if batch.status != "OPEN":
        raise ApiError(409, "batch_closed", "Remove items before the batch starts.")
    if item.removed_at is not None:
        return batch
    _claim_batch(db, batch, version)
    item.removed_at = _now()
    if item.garment_id is not None:
        garment = db.get(LaundryGarment, item.garment_id)
        if garment is not None and garment.current_batch_id == batch.id:
            garment.current_batch_id = None
    _recompute_load(db, batch)
    return batch


def _batch_status(
    db: Session, batch: LaundryBatch, expected: int, status: str, *, actor_store: uuid.UUID | None
) -> LaundryBatch:
    _branch(actor_store, batch.store_id)
    _claim_batch(db, batch, expected)
    batch.status = status
    if status == "STARTED":
        batch.started_at = _now()
    if status in {"COMPLETED", "ABORTED"}:
        batch.completed_at = _now()
    if status == "ABORTED":
        items = list(db.scalars(select(LaundryBatchItem).where(LaundryBatchItem.batch_id == batch.id)))
        for item in items:
            if item.removed_at is None:
                item.removed_at = _now()
            if item.garment_id is None:
                continue
            garment = db.get(LaundryGarment, item.garment_id)
            if garment is not None and garment.current_batch_id == batch.id:
                garment.current_batch_id = None
    return batch


def start_batch(db: Session, batch_id: uuid.UUID, *, version: int, actor_store: uuid.UUID | None) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "That batch does not exist.")
    if batch.status == "STARTED":
        return batch
    if batch.status != "OPEN":
        raise ApiError(409, "batch_closed", "This batch cannot be started.")
    return _batch_status(db, batch, version, "STARTED", actor_store=actor_store)


def complete_batch(db: Session, batch_id: uuid.UUID, *, version: int, actor_store: uuid.UUID | None) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "That batch does not exist.")
    if batch.status == "COMPLETED":
        return batch
    if batch.status != "STARTED":
        raise ApiError(409, "batch_closed", "Start the batch before completing it.")
    # Completing the load does not mark the garments or the order ready.
    return _batch_status(db, batch, version, "COMPLETED", actor_store=actor_store)


def abort_batch(
    db: Session,
    batch_id: uuid.UUID,
    *,
    version: int,
    reason: str,
    actor_store: uuid.UUID | None,
    actor_id: uuid.UUID | None,
) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    if batch is None:
        raise ApiError(404, "not_found", "That batch does not exist.")
    if batch.status == "ABORTED":
        return batch
    if batch.status not in {"OPEN", "STARTED"}:
        raise ApiError(409, "batch_closed", "This batch cannot be aborted.")
    if len(reason.strip()) < 3:
        raise ApiError(422, "reason_required", "Aborting a batch needs a reason.")
    _batch_status(db, batch, version, "ABORTED", actor_store=actor_store)
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.batch.abort",
        target_entity="LaundryBatch",
        target_entity_id=batch.id,
        user_id=actor_id,
        reason_notes=reason.strip(),
        details={"code": batch.code},
    )
    return batch


def list_batches(db: Session, store_id: uuid.UUID | None) -> list[dict]:
    rows = list(db.scalars(select(LaundryBatch).order_by(LaundryBatch.created_at.desc())))
    if store_id is not None:
        rows = [item for item in rows if item.store_id == store_id]
    result = []
    for batch in rows[:100]:
        count = int(
            db.scalar(
                select(func.count())
                .select_from(LaundryBatchItem)
                .where(LaundryBatchItem.batch_id == batch.id, LaundryBatchItem.removed_at.is_(None))
            )
            or 0
        )
        result.append(
            {
                "id": batch.id,
                "code": batch.code,
                "store_id": batch.store_id,
                "workflow_code": batch.workflow_code,
                "status": batch.status,
                "machine_id": batch.machine_id,
                "load_weight": batch.load_weight,
                "version": batch.version,
                "item_count": count,
            }
        )
    return result


def register_machine(
    db: Session, payload: MachineIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryMachine:
    if payload.machine_type not in MACHINE_TYPES:
        raise ApiError(422, "invalid_machine", "Choose a supported machine type.")
    _branch(actor_store, payload.store_id)
    code = payload.code.strip().upper()
    if db.scalar(select(LaundryMachine.id).where(LaundryMachine.code == code)) is not None:
        raise ApiError(409, "duplicate_machine", "That machine code already exists.")
    row = LaundryMachine(
        code=code,
        name=payload.name.strip(),
        machine_type=payload.machine_type,
        store_id=payload.store_id,
        plant_store_id=payload.plant_store_id,
        capacity=payload.capacity,
        capacity_unit=payload.capacity_unit.strip().upper() or "G",
        status="AVAILABLE",
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.machine",
        target_entity="LaundryMachine",
        target_entity_id=row.id,
        user_id=actor_id,
        details={"code": row.code, "type": row.machine_type},
    )
    return row


def update_machine(
    db: Session,
    machine_id: uuid.UUID,
    payload: MachinePatch,
    *,
    actor_id: uuid.UUID | None,
    actor_store: uuid.UUID | None,
) -> LaundryMachine:
    machine = db.get(LaundryMachine, machine_id)
    if machine is None:
        raise ApiError(404, "not_found", "That machine does not exist.")
    _branch(actor_store, machine.store_id)
    if payload.status and payload.status not in MACHINE_STATUSES:
        raise ApiError(422, "invalid_machine", "Choose a supported machine status.")
    if payload.status in {"MAINTENANCE", "OUT_OF_SERVICE", "DISABLED"} and machine.status == "RUNNING":
        raise ApiError(409, "machine_busy", "Finish or report the running cycle before taking the machine down.")
    if payload.capacity is not None and payload.capacity < 0:
        raise ApiError(422, "invalid_machine", "Capacity cannot be negative.")
    result = db.execute(
        update(LaundryMachine)
        .where(LaundryMachine.id == machine.id, LaundryMachine.version == payload.version)
        .values(version=payload.version + 1)
    )
    if result.rowcount != 1:
        raise ApiError(409, "machine_conflict", "This machine was updated by someone else.")
    machine.version = payload.version + 1
    if payload.name.strip():
        machine.name = payload.name.strip()
    if payload.status:
        machine.status = payload.status
    if payload.maintenance_note:
        machine.maintenance_note = payload.maintenance_note.strip()[:500]
    if payload.capacity is not None:
        machine.capacity = payload.capacity
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.machine",
        target_entity="LaundryMachine",
        target_entity_id=machine.id,
        user_id=actor_id,
        details={"status": machine.status},
    )
    return machine


def list_machines(db: Session, store_id: uuid.UUID | None) -> list[LaundryMachine]:
    rows = list(db.scalars(select(LaundryMachine).order_by(LaundryMachine.code)))
    if store_id is None:
        return rows
    return [item for item in rows if item.store_id == store_id]


def start_cycle(
    db: Session, machine_id: uuid.UUID, payload: CycleIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryMachineCycle:
    existing = db.scalar(
        select(LaundryMachineCycle).where(LaundryMachineCycle.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        return existing
    machine = db.get(LaundryMachine, machine_id)
    if machine is None:
        raise ApiError(404, "not_found", "That machine does not exist.")
    _branch(actor_store, machine.store_id)
    if machine.status != "AVAILABLE":
        raise ApiError(409, "machine_unavailable", "That machine is not available.")
    batch = None
    if payload.batch_id is not None:
        batch = db.get(LaundryBatch, payload.batch_id)
        if batch is None:
            raise ApiError(404, "not_found", "That batch does not exist.")
        _branch(actor_store, batch.store_id)
        if batch.status not in {"OPEN", "STARTED"}:
            raise ApiError(409, "batch_closed", "That batch is not active.")
        compatible = _MACHINE_WORKFLOWS.get(machine.machine_type)
        if compatible is not None and batch.workflow_code not in compatible:
            raise ApiError(422, "machine_workflow", "That machine does not run this workflow.")
        if batch.machine_id is not None and batch.machine_id != machine.id:
            current = db.get(LaundryMachine, batch.machine_id)
            if current is not None and current.status == "RUNNING":
                raise ApiError(409, "machine_busy", "The batch is already running on another machine.")
    if machine.capacity is not None:
        if payload.load_weight is None:
            raise ApiError(422, "measurement_required", "Enter the measured load. The server does not guess a weight.")
        if payload.load_weight > machine.capacity:
            raise ApiError(422, "over_capacity", "That load is above the machine capacity.")
    claimed = db.execute(
        update(LaundryMachine)
        .where(LaundryMachine.id == machine.id, LaundryMachine.status == "AVAILABLE")
        .values(status="RUNNING", version=machine.version + 1)
    )
    if claimed.rowcount != 1:
        raise ApiError(409, "machine_busy", "That machine was just assigned.")
    machine.status = "RUNNING"
    machine.version += 1
    cycle = LaundryMachineCycle(
        machine_id=machine.id,
        batch_id=payload.batch_id,
        cycle_code=payload.cycle_code.strip(),
        status="RUNNING",
        load_weight=payload.load_weight,
        idempotency_key=payload.idempotency_key,
        operator_id=actor_id,
        expected_at=payload.expected_at,
    )
    db.add(cycle)
    if batch is not None:
        batch.machine_id = machine.id
        if batch.status == "OPEN":
            batch.status = "STARTED"
            batch.started_at = _now()
    db.flush()
    return cycle


def complete_cycle(db: Session, cycle_id: uuid.UUID, *, actor_store: uuid.UUID | None) -> LaundryMachineCycle:
    cycle = db.get(LaundryMachineCycle, cycle_id)
    if cycle is None:
        raise ApiError(404, "not_found", "That cycle does not exist.")
    machine = db.get(LaundryMachine, cycle.machine_id)
    if machine is None:
        raise ApiError(404, "not_found", "That machine does not exist.")
    _branch(actor_store, machine.store_id)
    if cycle.status == "COMPLETED":
        return cycle
    if cycle.status != "RUNNING":
        raise ApiError(409, "cycle_closed", "That cycle is not running.")
    released = db.execute(
        update(LaundryMachine)
        .where(LaundryMachine.id == machine.id, LaundryMachine.status == "RUNNING")
        .values(status="AVAILABLE", version=machine.version + 1)
    )
    if released.rowcount != 1:
        raise ApiError(409, "machine_conflict", "The machine status changed.")
    machine.status = "AVAILABLE"
    machine.version += 1
    cycle.status = "COMPLETED"
    cycle.completed_at = _now()
    return cycle


def fault_cycle(
    db: Session, cycle_id: uuid.UUID, *, reason: str, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryMachineCycle:
    cycle = db.get(LaundryMachineCycle, cycle_id)
    if cycle is None:
        raise ApiError(404, "not_found", "That cycle does not exist.")
    machine = db.get(LaundryMachine, cycle.machine_id)
    if machine is None:
        raise ApiError(404, "not_found", "That machine does not exist.")
    _branch(actor_store, machine.store_id)
    if cycle.status == "FAILED":
        return cycle
    if cycle.status != "RUNNING":
        raise ApiError(409, "cycle_closed", "That cycle is not running.")
    if len(reason.strip()) < 3:
        raise ApiError(422, "reason_required", "A machine fault needs a reason.")
    machine.status = "OUT_OF_SERVICE"
    machine.version += 1
    machine.maintenance_note = reason.strip()[:500]
    cycle.status = "FAILED"
    cycle.issue = reason.strip()[:500]
    cycle.completed_at = _now()
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.machine.fault",
        target_entity="LaundryMachine",
        target_entity_id=machine.id,
        user_id=actor_id,
        reason_notes=reason.strip(),
        details={"cycle_id": str(cycle.id)},
    )
    return cycle


def reassign_batch_machine(
    db: Session, batch_id: uuid.UUID, machine_id: uuid.UUID, *, version: int, actor_store: uuid.UUID | None
) -> LaundryBatch:
    batch = db.get(LaundryBatch, batch_id)
    machine = db.get(LaundryMachine, machine_id)
    if batch is None or machine is None:
        raise ApiError(404, "not_found", "That batch or machine does not exist.")
    _branch(actor_store, batch.store_id)
    _branch(actor_store, machine.store_id)
    if machine.status != "AVAILABLE":
        raise ApiError(409, "machine_unavailable", "That machine is not available.")
    if batch.machine_id is not None:
        current = db.get(LaundryMachine, batch.machine_id)
        if current is not None and current.status == "RUNNING":
            raise ApiError(409, "machine_busy", "Stop the running machine before reassigning the batch.")
    compatible = _MACHINE_WORKFLOWS.get(machine.machine_type)
    if compatible is not None and batch.workflow_code not in compatible:
        raise ApiError(422, "machine_workflow", "That machine does not run this workflow.")
    _claim_batch(db, batch, version)
    batch.machine_id = machine.id
    return batch


def inspect(
    db: Session, payload: InspectionIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryInspection:
    existing = db.scalar(select(LaundryInspection).where(LaundryInspection.idempotency_key == payload.idempotency_key))
    if existing is not None:
        return existing
    if payload.result not in QC_RESULTS:
        raise ApiError(422, "invalid_inspection", "Choose pass, fail, rework, or manager review.")
    if set(payload.checklist) != set(_CHECKLIST) or any(
        not isinstance(item, bool) for item in payload.checklist.values()
    ):
        raise ApiError(422, "invalid_checklist", "Complete every inspection point.")
    if payload.result != "PASS" and len(payload.reason.strip()) < 3:
        raise ApiError(422, "reason_required", "A failed inspection needs a reason.")
    garment = _garment(db, payload.garment_id)
    order = get_order(db, garment.order_id)
    _open_order(order)
    _branch(actor_store, garment.location_store_id or order.intake_store_id)
    if garment.stage != "QUALITY_CHECK":
        raise ApiError(422, "wrong_workflow", "Inspect the garment when it is at quality check.")
    chain = _chain(db, garment.workflow_code)
    required = payload.required_stage.strip().upper()
    if payload.result in {"FAIL", "REWORK_REQUIRED"}:
        if (
            "QUALITY_CHECK" not in chain
            or required not in chain
            or chain.index(required) >= chain.index("QUALITY_CHECK")
        ):
            raise ApiError(422, "wrong_workflow", "Send rework back to an earlier stage in the workflow.")
    _claim_garment(db, garment, payload.version)
    row = LaundryInspection(
        garment_id=garment.id,
        order_id=order.id,
        result=payload.result,
        checklist=payload.checklist,
        reason=payload.reason.strip(),
        idempotency_key=payload.idempotency_key,
        actor_id=actor_id,
    )
    db.add(row)
    db.flush()
    if payload.result == "PASS":
        garment.qc_result = "PASS"
        open_tasks = list(
            db.scalars(
                select(LaundryReworkTask).where(
                    LaundryReworkTask.garment_id == garment.id, LaundryReworkTask.status == "OPEN"
                )
            )
        )
        for task in open_tasks:
            task.status = "DONE"
            task.completed_at = _now()
    elif payload.result == "MANAGER_REVIEW":
        garment.qc_result = "MANAGER_REVIEW"
        garment.hold = True
    else:
        garment.qc_result = payload.result
        garment.stage = required
        garment.stage_entered_at = _now()
        garment.rework_count += 1
        db.add(
            LaundryReworkTask(
                garment_id=garment.id,
                order_id=order.id,
                inspection_id=row.id,
                reason=payload.reason.strip(),
                required_stage=required,
                assigned_user_id=actor_id,
                status="OPEN",
            )
        )
        db.add(
            LaundryStageEvent(
                garment_id=garment.id,
                order_id=order.id,
                from_stage="QUALITY_CHECK",
                to_stage=required,
                idempotency_key=f"rework:{payload.idempotency_key}",
                reason=payload.reason.strip()[:500],
                actor_id=actor_id,
                store_id=garment.location_store_id,
            )
        )
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.inspection",
        target_entity="LaundryInspection",
        target_entity_id=row.id,
        user_id=actor_id,
        reason_notes=payload.reason.strip() or None,
        details={"result": payload.result, "garment_id": str(garment.id)},
    )
    _refresh_order(db, order, actor_id)
    return row


def complete_rework(db: Session, task_id: uuid.UUID, *, note: str, actor_id: uuid.UUID | None) -> LaundryReworkTask:
    task = db.get(LaundryReworkTask, task_id)
    if task is None:
        raise ApiError(404, "not_found", "That rework task does not exist.")
    if task.status == "DONE":
        return task
    garment = _garment(db, task.garment_id)
    if garment.stage != "QUALITY_CHECK":
        raise ApiError(422, "wrong_workflow", "Return the garment to quality check before closing rework.")
    task.status = "DONE"
    task.completed_at = _now()
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.rework.complete",
        target_entity="LaundryReworkTask",
        target_entity_id=task.id,
        user_id=actor_id,
        reason_notes=note.strip() or None,
        details={"garment_id": str(garment.id)},
    )
    return task


def report_incident(
    db: Session, payload: IncidentIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryIncident:
    if payload.kind not in INCIDENT_KINDS:
        raise ApiError(422, "invalid_incident", "Choose a supported incident type.")
    order = get_order(db, payload.order_id)
    _branch(actor_store, order.intake_store_id)
    garment = None
    if payload.garment_id is not None:
        garment = _garment(db, payload.garment_id)
        if garment.order_id != order.id:
            raise ApiError(422, "wrong_order", "That garment is not on this order.")
    row = LaundryIncident(
        order_id=order.id,
        garment_id=payload.garment_id,
        batch_id=payload.batch_id,
        kind=payload.kind,
        stage=garment.stage if garment is not None else "",
        location=payload.location.strip()[:80],
        description=payload.description.strip(),
        status="OPEN",
        blocks_ready=payload.blocks_ready,
        actor_id=actor_id,
    )
    db.add(row)
    if payload.blocks_ready and garment is not None:
        garment.hold = True
    if order.claim_status == "NONE" and payload.kind in {"MISSING", "DAMAGED", "PROCESSING_DAMAGE"}:
        order.claim_status = "OPEN"
    paid_before = order.amount_paid_cents
    deposits = int(
        db.scalar(select(func.count()).select_from(LaundryDeposit).where(LaundryDeposit.order_id == order.id)) or 0
    )
    audit.record(
        db,
        action_type="CREATE",
        action="laundry.incident",
        target_entity="LaundryIncident",
        target_entity_id=row.id,
        user_id=actor_id,
        details={"kind": payload.kind, "order_id": str(order.id), "paid_cents": paid_before, "deposits": deposits},
    )
    db.flush()
    return row


def resolve_incident(
    db: Session,
    incident_id: uuid.UUID,
    *,
    status: str,
    resolution: str,
    actor_id: uuid.UUID | None,
    actor_store: uuid.UUID | None,
) -> LaundryIncident:
    if status not in {"INVESTIGATING", "RESOLVED", "CLOSED"}:
        raise ApiError(422, "invalid_incident", "Choose investigating, resolved, or closed.")
    row = db.get(LaundryIncident, incident_id)
    if row is None:
        raise ApiError(404, "not_found", "That incident does not exist.")
    order = get_order(db, row.order_id)
    _branch(actor_store, order.intake_store_id)
    row.status = status
    row.resolution = resolution.strip()
    if status in {"RESOLVED", "CLOSED"}:
        row.blocks_ready = False
        row.resolved_at = _now()
        if row.garment_id is not None:
            garment = db.get(LaundryGarment, row.garment_id)
            still = db.scalar(
                select(LaundryIncident.id).where(
                    LaundryIncident.garment_id == row.garment_id,
                    LaundryIncident.id != row.id,
                    LaundryIncident.blocks_ready.is_(True),
                    LaundryIncident.status.in_(("OPEN", "INVESTIGATING")),
                )
            )
            if garment is not None and still is None:
                garment.hold = False
        open_claims = db.scalar(
            select(LaundryIncident.id).where(
                LaundryIncident.order_id == order.id,
                LaundryIncident.status.in_(("OPEN", "INVESTIGATING")),
            )
        )
        if open_claims is None and order.claim_status == "OPEN":
            order.claim_status = "RESOLVED"
    audit.record(
        db,
        action_type="UPDATE",
        action="laundry.incident.resolve",
        target_entity="LaundryIncident",
        target_entity_id=row.id,
        user_id=actor_id,
        reason_notes=resolution.strip(),
        details={"status": status, "refund": False},
    )
    return row


def list_incidents(db: Session, store_id: uuid.UUID | None) -> list[LaundryIncident]:
    rows = list(db.scalars(select(LaundryIncident).order_by(LaundryIncident.created_at.desc())))
    if store_id is None:
        return rows[:100]
    orders = {item.id: item for item in db.scalars(select(LaundryOrder))}
    return [item for item in rows if item.order_id in orders and orders[item.order_id].intake_store_id == store_id][
        :100
    ]


def pack_scan(
    db: Session, payload: PackingScanIn, *, actor_id: uuid.UUID | None, actor_store: uuid.UUID | None
) -> LaundryPackingScan:
    existing = db.scalar(
        select(LaundryPackingScan).where(LaundryPackingScan.idempotency_key == payload.idempotency_key)
    )
    if existing is not None:
        return existing
    garment = _garment(db, payload.garment_id)
    order = get_order(db, payload.order_id)
    if garment.order_id != order.id:
        raise ApiError(422, "wrong_order", "That garment belongs to a different order.")
    _branch(actor_store, garment.location_store_id or order.intake_store_id)
    _open_order(order)
    if garment.stage != "PACKING":
        raise ApiError(422, "incomplete_processing", "Finish the workflow and pass inspection before packing.")
    chain = _chain(db, garment.workflow_code)
    if "QUALITY_CHECK" in chain and garment.qc_result != "PASS":
        raise ApiError(422, "failed_qc", "A garment that failed inspection cannot be packed.")
    if garment.hold or _blocking(db, order.id):
        raise ApiError(422, "incident_hold", "An open incident is holding this garment.")
    duplicate = db.scalar(
        select(LaundryPackingScan.id).where(
            LaundryPackingScan.garment_id == garment.id,
            LaundryPackingScan.rework_count == garment.rework_count,
        )
    )
    if duplicate is not None:
        raise ApiError(409, "duplicate_scan", "That garment is already in this packing.")
    _claim_garment(db, garment, payload.version)
    row = LaundryPackingScan(
        order_id=order.id,
        garment_id=garment.id,
        bag_code=payload.bag_code.strip()[:40],
        rework_count=garment.rework_count,
        idempotency_key=payload.idempotency_key,
        actor_id=actor_id,
    )
    db.add(row)
    db.flush()
    return row


def complete_packing(
    db: Session,
    order_id: uuid.UUID,
    *,
    idempotency_key: str,
    actor_id: uuid.UUID | None,
    actor_store: uuid.UUID | None,
    permissions: frozenset[str],
) -> LaundryOrder:
    order = get_order(db, order_id)
    _branch(actor_store, order.intake_store_id)
    _open_order(order)
    if order.operational_status == "READY_FOR_COLLECTION":
        return order
    garments = list(db.scalars(select(LaundryGarment).where(LaundryGarment.order_id == order.id)))
    if not garments:
        raise ApiError(422, "not_packed", "This order has no garments to pack.")
    if _blocking(db, order.id) or any(item.hold for item in garments):
        raise ApiError(422, "incident_hold", "Resolve the holding incident before the order is ready.")
    for garment in garments:
        chain = _chain(db, garment.workflow_code)
        if garment.stage != "PACKING":
            raise ApiError(422, "incomplete_processing", "Every garment has to be at packing.")
        if "QUALITY_CHECK" in chain and garment.qc_result != "PASS":
            raise ApiError(422, "failed_qc", "Every garment needs a passing inspection.")
        packed = db.scalar(
            select(LaundryPackingScan.id).where(
                LaundryPackingScan.garment_id == garment.id,
                LaundryPackingScan.rework_count == garment.rework_count,
            )
        )
        if packed is None:
            raise ApiError(422, "not_packed", "Scan every garment into the packing bag.")
        key = f"{idempotency_key}:{garment.id}"
        seen = db.scalar(select(LaundryStageEvent).where(LaundryStageEvent.idempotency_key == key))
        if seen is None:
            payload = TransitionIn(
                target="READY_FOR_COLLECTION", version=garment.version, idempotency_key=key, reason="Packed"
            )
            transition(db, garment.id, payload, actor_id=actor_id, actor_store=actor_store, permissions=permissions)
    return get_order(db, order.id)
