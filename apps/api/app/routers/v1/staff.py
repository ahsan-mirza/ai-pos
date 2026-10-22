import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.staff import (
    CommissionReport,
    CommissionRuleOut,
    CommissionRuleWrite,
    EmployeeOut,
    EmployeeProfileWrite,
    PayrollLineWrite,
    PayrollRunCreate,
    PayrollRunOut,
    PayrollSettings,
)
from app.services import staff_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanStaff = Annotated[Principal, Depends(authorize(Permission.STAFF_MANAGE))]
CanPayroll = Annotated[Principal, Depends(authorize(Permission.PAYROLL_MANAGE))]


def _user(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user else None


@router.get("/commission-rules", response_model=list[CommissionRuleOut])
def rules(db: Db, _: CanStaff) -> list[CommissionRuleOut]:
    return staff_service.list_rules(db)


@router.post("/commission-rules", response_model=CommissionRuleOut, status_code=201)
def create_rule(payload: CommissionRuleWrite, db: Db, _: CanStaff) -> CommissionRuleOut:
    return staff_service.save_rule(db, payload)


@router.put("/commission-rules/{rule_id}", response_model=CommissionRuleOut)
def update_rule(rule_id: uuid.UUID, payload: CommissionRuleWrite, db: Db, _: CanStaff) -> CommissionRuleOut:
    return staff_service.save_rule(db, payload, rule_id)


@router.get("/commissions", response_model=CommissionReport)
def commissions(
    db: Db,
    principal: CanStaff,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
) -> CommissionReport:
    return staff_service.commissions(db, start=start, end=end, store_id=principal.store_id or store_id)


@router.get("/payroll/settings", response_model=PayrollSettings | None)
def payroll_settings(db: Db, _: CanPayroll) -> PayrollSettings | None:
    return staff_service.payroll_settings(db)


@router.put("/payroll/settings", response_model=PayrollSettings)
def save_payroll_settings(payload: PayrollSettings, db: Db, _: CanPayroll) -> PayrollSettings:
    return staff_service.save_payroll_settings(db, payload)


@router.get("/employees", response_model=list[EmployeeOut])
def employees(db: Db, _: CanPayroll) -> list[EmployeeOut]:
    return staff_service.employees(db)


@router.put("/employees/{user_id}", response_model=list[EmployeeOut])
def save_employee(user_id: uuid.UUID, payload: EmployeeProfileWrite, db: Db, _: CanPayroll) -> list[EmployeeOut]:
    return staff_service.save_profile(db, user_id, payload)


@router.get("/payroll/runs", response_model=list[PayrollRunOut])
def runs(db: Db, _: CanPayroll) -> list[PayrollRunOut]:
    return staff_service.list_runs(db)


@router.post("/payroll/runs", response_model=PayrollRunOut, status_code=201)
def create_run(payload: PayrollRunCreate, db: Db, principal: CanPayroll) -> PayrollRunOut:
    return staff_service.create_run(db, payload.year, payload.month, _user(principal))


@router.post("/payroll/runs/{run_id}/recalculate", response_model=PayrollRunOut)
def recalculate(run_id: uuid.UUID, db: Db, _: CanPayroll) -> PayrollRunOut:
    return staff_service.recalculate(db, run_id)


@router.put("/payroll/runs/{run_id}/lines/{line_id}", response_model=PayrollRunOut)
def update_line(
    run_id: uuid.UUID, line_id: uuid.UUID, payload: PayrollLineWrite, db: Db, _: CanPayroll
) -> PayrollRunOut:
    return staff_service.update_line(db, run_id, line_id, payload)


@router.post("/payroll/runs/{run_id}/finalize", response_model=PayrollRunOut)
def finalize(run_id: uuid.UUID, db: Db, principal: CanPayroll) -> PayrollRunOut:
    return staff_service.finalize(db, run_id, _user(principal))


@router.get("/payroll/runs/{run_id}/wps.sif", response_class=Response)
def wps(run_id: uuid.UUID, db: Db, _: CanPayroll) -> Response:
    name, body = staff_service.wps_file(db, run_id)
    return Response(body, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{name}"'})
