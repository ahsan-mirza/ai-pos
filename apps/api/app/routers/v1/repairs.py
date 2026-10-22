import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.routers.v1.deps import assert_store_access, require_device_id, require_idempotency_key
from app.schemas.payloads import RepairOut, RepairPayload
from app.schemas.repairs import RepairDetail, RepairInvoiceCreate, RepairLineCreate, RepairStatusChange
from app.services import catalog_service, repair_service
from app.services.sync_service import ingest_one

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanUpdate = Annotated[Principal, Depends(authorize(Permission.REPAIRS_UPDATE))]


@router.get("", response_model=list[RepairOut])
def list_repairs(
    db: Db,
    settings: Config,
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True))],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RepairOut]:
    return catalog_service.list_repairs(db, settings, limit=limit, store_scope=principal.store_id)


@router.post("", response_model=RepairOut, status_code=201)
def create_repair(
    payload: RepairPayload,
    response: Response,
    db: Db,
    settings: Config,
    principal: Annotated[
        Principal,
        Depends(authorize(Permission.REPAIRS_CREATE, allow_device=True, scopes=("portal", "pos"))),
    ],
    device_id: Annotated[str, Depends(require_device_id)],
    idempotency_key: Annotated[str, Depends(require_idempotency_key)],
) -> RepairOut:
    assert_store_access(principal, payload.store_id)
    result = ingest_one(
        db,
        settings,
        device_id=device_id,
        idempotency_key=idempotency_key,
        entity_type="repair_ticket",
        payload=payload,
    )
    if result.results[0].status == "duplicate":
        response.status_code = 200
    return catalog_service.get_repair(db, settings, payload.id)


@router.get("/{ticket_id}", response_model=RepairDetail)
def repair_detail(
    ticket_id: uuid.UUID,
    db: Db,
    settings: Config,
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))],
) -> RepairDetail:
    return repair_service.detail(db, settings, ticket_id, principal.store_id)


@router.post("/{ticket_id}/status", response_model=RepairDetail)
def change_status(
    ticket_id: uuid.UUID, payload: RepairStatusChange, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    return repair_service.change_status(db, settings, principal, ticket_id, payload)


@router.post("/{ticket_id}/lines", response_model=RepairDetail, status_code=201)
def add_line(
    ticket_id: uuid.UUID, payload: RepairLineCreate, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    return repair_service.add_line(db, settings, principal, ticket_id, payload)


@router.delete("/{ticket_id}/lines/{line_id}", response_model=RepairDetail)
def remove_line(
    ticket_id: uuid.UUID, line_id: uuid.UUID, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    return repair_service.remove_line(db, settings, principal, ticket_id, line_id)


@router.post("/{ticket_id}/invoice", response_model=RepairDetail)
def invoice_repair(
    ticket_id: uuid.UUID, payload: RepairInvoiceCreate, db: Db, settings: Config, principal: CanUpdate
) -> RepairDetail:
    return repair_service.invoice(db, settings, principal, ticket_id, payload)
