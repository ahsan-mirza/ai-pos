"""Customer reorder plans and the reminders they raise. Tenant comes from the signed-in store."""

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, get_principal
from app.core.pagination import Offset, set_total
from app.core.permissions import Permission
from app.schemas.reorders import (
    DraftOrderIn,
    LinkOrderIn,
    OccurrenceOut,
    PlanIn,
    PlanOut,
    PlanUpdate,
    SkipIn,
    SnoozeIn,
    SummaryOut,
)
from app.schemas.sales_orders import SalesOrderOut
from app.services import reorder_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]


def _view(principal: Annotated[Principal, Depends(get_principal)]) -> Principal:
    if principal.kind == "device":
        return principal
    if principal.scope not in {"portal", "pos"}:
        raise_forbidden()
    allowed = {Permission.CUSTOMERS_MANAGE.value, Permission.POS_ACCESS.value}
    if not allowed & set(principal.permissions):
        raise_forbidden()
    return principal


def raise_forbidden() -> None:
    from app.core.errors import ApiError

    raise ApiError(403, "forbidden", "You do not have permission for this action.")


CanView = Annotated[Principal, Depends(_view)]
CanEdit = Annotated[Principal, Depends(authorize(Permission.CUSTOMERS_MANAGE))]


@router.get("/summary", response_model=SummaryOut)
def summary(db: Db, _: CanView) -> SummaryOut:
    return reorder_service.summary(db)


@router.get("/plans", response_model=list[PlanOut])
def list_plans(
    db: Db,
    _: CanView,
    response: Response,
    offset: Offset,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    customer_id: uuid.UUID | None = None,
    salesperson_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[PlanOut]:
    rows, total = reorder_service.list_plans(
        db,
        offset=offset,
        limit=limit,
        q=q,
        status=status,
        customer_id=customer_id,
        salesperson_id=salesperson_id,
        store_id=store_id,
    )
    set_total(response, total)
    return rows


@router.post("/plans", response_model=PlanOut, status_code=201)
def create_plan(data: PlanIn, db: Db, principal: CanEdit) -> PlanOut:
    return reorder_service.create_plan(db, principal, data)


@router.get("/plans/{plan_id}", response_model=PlanOut)
def get_plan(plan_id: uuid.UUID, db: Db, _: CanView) -> PlanOut:
    return reorder_service.get_plan(db, plan_id)


@router.patch("/plans/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, data: PlanUpdate, db: Db, principal: CanEdit) -> PlanOut:
    return reorder_service.update_plan(db, principal, plan_id, data)


@router.post("/plans/{plan_id}/pause", response_model=PlanOut)
def pause_plan(plan_id: uuid.UUID, db: Db, principal: CanEdit) -> PlanOut:
    return reorder_service.pause_plan(db, principal, plan_id)


@router.post("/plans/{plan_id}/resume", response_model=PlanOut)
def resume_plan(plan_id: uuid.UUID, db: Db, principal: CanEdit) -> PlanOut:
    return reorder_service.resume_plan(db, principal, plan_id)


@router.post("/plans/{plan_id}/archive", response_model=PlanOut)
def archive_plan(plan_id: uuid.UUID, db: Db, principal: CanEdit) -> PlanOut:
    return reorder_service.archive_plan(db, principal, plan_id)


@router.get("/occurrences", response_model=list[OccurrenceOut])
def list_occurrences(
    db: Db,
    _: CanView,
    response: Response,
    offset: Offset,
    q: Annotated[str | None, Query(max_length=80)] = None,
    status: Annotated[str | None, Query(max_length=16)] = None,
    customer_id: uuid.UUID | None = None,
    salesperson_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    view: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[OccurrenceOut]:
    rows, total = reorder_service.list_occurrences(
        db,
        offset=offset,
        limit=limit,
        q=q,
        status=status,
        customer_id=customer_id,
        salesperson_id=salesperson_id,
        store_id=store_id,
        date_from=date_from,
        date_to=date_to,
        view=view,
    )
    set_total(response, total)
    return rows


@router.post("/occurrences/{occurrence_id}/snooze", response_model=OccurrenceOut)
def snooze(occurrence_id: uuid.UUID, data: SnoozeIn, db: Db, principal: CanView) -> OccurrenceOut:
    return reorder_service.snooze(db, principal, occurrence_id, data)


@router.post("/occurrences/{occurrence_id}/skip", response_model=OccurrenceOut)
def skip(occurrence_id: uuid.UUID, data: SkipIn, db: Db, principal: CanView) -> OccurrenceOut:
    return reorder_service.skip(db, principal, occurrence_id, data)


@router.post("/occurrences/{occurrence_id}/order", response_model=SalesOrderOut)
def create_order(occurrence_id: uuid.UUID, data: DraftOrderIn, db: Db, principal: CanView) -> SalesOrderOut:
    return reorder_service.create_draft(db, principal, occurrence_id, data)


@router.post("/occurrences/{occurrence_id}/link", response_model=OccurrenceOut)
def link_order(occurrence_id: uuid.UUID, data: LinkOrderIn, db: Db, principal: CanView) -> OccurrenceOut:
    return reorder_service.link_order(db, principal, occurrence_id, data)


@router.post("/occurrences/{occurrence_id}/complete", response_model=OccurrenceOut)
def complete(occurrence_id: uuid.UUID, db: Db, principal: CanView) -> OccurrenceOut:
    return reorder_service.complete(db, principal, occurrence_id)


@router.post("/occurrences/{occurrence_id}/retry-notification", response_model=OccurrenceOut)
def retry_notification(occurrence_id: uuid.UUID, db: Db, principal: CanEdit) -> OccurrenceOut:
    del principal
    return reorder_service.retry_notification(db, occurrence_id)
