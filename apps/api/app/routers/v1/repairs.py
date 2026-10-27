import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.routers.v1.deps import assert_store_access, require_device_id, require_idempotency_key
from app.schemas.payloads import RepairOut, RepairPayload
from app.schemas.repairs import (
    RepairDetail,
    RepairDeviceHit,
    RepairInvoiceCreate,
    RepairLineCreate,
    RepairStatusChange,
)
from app.services import catalog_service, repair_service
from app.services.sync_service import ingest_one

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanUpdate = Annotated[Principal, Depends(authorize(Permission.REPAIRS_UPDATE))]


@router.get("", response_model=list[RepairOut])
def list_repairs(
    response: Response,
    db: Db,
    settings: Config,
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True))],
    offset: Offset,
    limit: Annotated[int, Query(ge=1, le=200)] = 25,
    q: Annotated[str, Query(max_length=80)] = "",
    status: Annotated[str | None, Query(max_length=24)] = None,
    ownership: Annotated[str | None, Query(max_length=12)] = None,
    technician_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    received_from: Annotated[str | None, Query(max_length=32)] = None,
    received_to: Annotated[str | None, Query(max_length=32)] = None,
    promised_from: Annotated[str | None, Query(max_length=32)] = None,
    promised_to: Annotated[str | None, Query(max_length=32)] = None,
    overdue: bool = False,
    warranty: bool = False,
    active: bool = False,
    sort: Annotated[str, Query(max_length=16)] = "received",
    direction: Annotated[str, Query(max_length=4)] = "desc",
) -> list[RepairOut]:
    rows, total = repair_service.search_tickets(
        db,
        settings,
        store_scope=principal.store_id,
        store_id=store_id,
        query=q,
        status=status,
        ownership=ownership,
        technician_id=technician_id,
        received_from=received_from,
        received_to=received_to,
        promised_from=promised_from,
        promised_to=promised_to,
        overdue=overdue,
        warranty=warranty,
        active=active,
        sort=sort,
        direction=direction,
        offset=offset,
        limit=limit,
        financial=principal.has(Permission.ACCOUNTING_MANAGE),
    )
    set_total(response, total)
    return rows


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


@router.get("/matches", response_model=list[RepairOut])
def match_open_repairs(
    db: Db,
    settings: Config,
    principal: Annotated[
        Principal,
        Depends(authorize(Permission.REPAIRS_CREATE, allow_device=True, scopes=("portal", "pos"))),
    ],
    phone: Annotated[str, Query(max_length=40)] = "",
    identifier: Annotated[str, Query(max_length=64)] = "",
    customer_name: Annotated[str, Query(max_length=120)] = "",
) -> list[RepairOut]:
    """Possible duplicates. Booking is not blocked; the counter confirms a genuine repeat repair."""
    return repair_service.matching_open_repairs(
        db,
        settings,
        store_scope=principal.store_id,
        phone=phone,
        identifier=identifier,
        customer_name=customer_name,
    )


@router.get("/devices", response_model=list[RepairDeviceHit])
def search_repair_devices(
    db: Db,
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True))],
    q: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[RepairDeviceHit]:
    return repair_service.search_devices(db, q, limit=limit, store_id=principal.store_id)


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
