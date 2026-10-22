from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.manager import CreditHoldRow, ManagerDashboard, PendingTimeEntry
from app.services import manager_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]
CanStaff = Annotated[Principal, Depends(authorize(Permission.STAFF_MANAGE))]
CanCustomers = Annotated[Principal, Depends(authorize(Permission.CUSTOMERS_MANAGE))]


@router.get("/dashboard", response_model=ManagerDashboard)
def dashboard(
    db: Db,
    principal: CanRead,
    tz_offset_minutes: Annotated[int, Query(ge=-720, le=840)] = 240,
) -> ManagerDashboard:
    return manager_service.dashboard(db, principal, tz_offset_minutes)


@router.get("/timesheets", response_model=list[PendingTimeEntry])
def timesheets(db: Db, principal: CanStaff) -> list[PendingTimeEntry]:
    return manager_service.pending_timesheets(db, principal)


@router.get("/credit-holds", response_model=list[CreditHoldRow])
def credit_holds(db: Db, _: CanCustomers) -> list[CreditHoldRow]:
    return manager_service.credit_holds(db)
