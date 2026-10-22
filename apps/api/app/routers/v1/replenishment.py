import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.replenishment import (
    AcceptRequest,
    AcceptResult,
    LeadTimeWrite,
    RunCreate,
    RunOut,
    SeasonalEventOut,
    SeasonalEventWrite,
    SupplierLeadOut,
    SupplierTermsWrite,
)
from app.services import replenishment_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.REPLENISHMENT_MANAGE))]


def _store(principal: Principal, store_id: uuid.UUID) -> uuid.UUID:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only plan replenishment for your own store.")
    return store_id


@router.post("/runs", response_model=RunOut, status_code=201)
def create_run(payload: RunCreate, db: Db, principal: CanManage) -> RunOut:
    return replenishment_service.create_run(
        db,
        store_id=_store(principal, payload.store_id),
        review_days=payload.review_days,
        user_id=principal.user.id if principal.user else None,
        split_by_size_curve=payload.split_by_size_curve,
    )


@router.get("/runs/latest", response_model=RunOut | None)
def latest(db: Db, principal: CanManage, store_id: uuid.UUID):
    return replenishment_service.latest_run(db, _store(principal, store_id))


@router.post("/runs/{run_id}/accept", response_model=AcceptResult)
def accept(
    run_id: uuid.UUID,
    payload: AcceptRequest,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanManage,
) -> AcceptResult:
    return replenishment_service.accept(
        db, settings, principal, run_id, {line.id: line.quantity for line in payload.lines}
    )


@router.post("/suggestions/{suggestion_id}/dismiss", response_model=RunOut)
def dismiss(suggestion_id: uuid.UUID, db: Db, _: CanManage) -> RunOut:
    return replenishment_service.dismiss(db, suggestion_id)


@router.get("/events", response_model=list[SeasonalEventOut])
def events(db: Db, _: CanManage) -> list[SeasonalEventOut]:
    return replenishment_service.list_events(db)


@router.post("/events", response_model=list[SeasonalEventOut], status_code=201)
def create_event(payload: SeasonalEventWrite, db: Db, _: CanManage) -> list[SeasonalEventOut]:
    return replenishment_service.save_event(db, payload)


@router.delete("/events/{event_id}", response_model=list[SeasonalEventOut])
def delete_event(event_id: uuid.UUID, db: Db, _: CanManage) -> list[SeasonalEventOut]:
    return replenishment_service.delete_event(db, event_id)


@router.get("/suppliers", response_model=list[SupplierLeadOut])
def suppliers(db: Db, _: CanManage) -> list[SupplierLeadOut]:
    return replenishment_service.suppliers(db)


@router.put("/suppliers/{supplier_id}/lead-time", response_model=list[SupplierLeadOut])
def lead_time(supplier_id: uuid.UUID, payload: LeadTimeWrite, db: Db, _: CanManage) -> list[SupplierLeadOut]:
    return replenishment_service.set_lead_time(db, supplier_id, payload.lead_time_days)


@router.put("/suppliers/{supplier_id}/terms", response_model=list[SupplierLeadOut])
def supplier_terms(supplier_id: uuid.UUID, payload: SupplierTermsWrite, db: Db, _: CanManage) -> list[SupplierLeadOut]:
    return replenishment_service.set_terms(db, supplier_id, payload)
