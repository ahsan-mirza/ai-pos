import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.timesheets import TimeEntryWrite, TimesheetApprove, TimesheetReport
from app.services import timesheet_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.STAFF_MANAGE))]


@router.get("", response_model=TimesheetReport)
def timesheets(
    db: Db,
    principal: CanManage,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> TimesheetReport:
    return timesheet_service.report(
        db, start=start, end=end, store_scope=principal.store_id or store_id, user_id=user_id
    )


@router.post("/entries", status_code=201)
def add_entry(payload: TimeEntryWrite, db: Db, principal: CanManage) -> dict[str, bool]:
    timesheet_service.add_manual(db, principal, payload)
    return {"ok": True}


@router.put("/entries/{entry_id}")
def correct_entry(entry_id: uuid.UUID, payload: TimeEntryWrite, db: Db, principal: CanManage) -> dict[str, bool]:
    timesheet_service.correct(db, principal, entry_id, payload)
    return {"ok": True}


@router.post("/approve")
def approve(payload: TimesheetApprove, db: Db, principal: CanManage) -> dict[str, int]:
    return {"approved": timesheet_service.approve(db, principal, payload.entry_ids)}
