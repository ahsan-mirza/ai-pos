import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize, authorize_any, get_principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.staff import (
    CommissionReport,
    CommissionRuleOut,
    CommissionRuleWrite,
    EmployeeOut,
    EmployeeProfileWrite,
    PayrollLineWrite,
    PayrollNote,
    PayrollPaymentOut,
    PayrollPaymentWrite,
    PayrollRunCreate,
    PayrollRunOut,
    PayrollSettings,
    PayslipSummary,
    SalaryVersionOut,
    WpsValidation,
)
from app.services import payroll_payslip, staff_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanStaff = Annotated[Principal, Depends(authorize(Permission.STAFF_MANAGE))]
CanView = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_VIEW))]
CanProfiles = Annotated[
    Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_MANAGE_PROFILES))
]
CanCalculate = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_CALCULATE))]
CanSubmit = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_SUBMIT))]
CanApprove = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_APPROVE))]
CanWps = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_GENERATE_WPS))]
CanPay = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_RECORD_PAYMENT))]
CanExport = Annotated[Principal, Depends(authorize_any(Permission.PAYROLL_MANAGE, Permission.PAYROLL_EXPORT))]
PortalUser = Annotated[Principal, Depends(get_principal)]


def _user(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user else None


def _home(principal: Principal) -> uuid.UUID | None:
    return principal.store_id


def _sees_bank(principal: Principal) -> bool:
    allowed = {
        Permission.PAYROLL_MANAGE.value,
        Permission.PAYROLL_MANAGE_PROFILES.value,
        Permission.PAYROLL_VIEW_SENSITIVE.value,
    }
    return bool(allowed & set(principal.permissions))


def _can_read_pay(principal: Principal, employee_id: uuid.UUID) -> bool:
    if principal.user is not None and principal.user.id == employee_id:
        return True
    allowed = {Permission.PAYROLL_MANAGE.value, Permission.PAYROLL_VIEW.value, Permission.PAYROLL_EXPORT.value}
    return bool(allowed & set(principal.permissions))


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
def payroll_settings(db: Db, _: CanView) -> PayrollSettings | None:
    return staff_service.payroll_settings(db)


@router.put("/payroll/settings", response_model=PayrollSettings)
def save_payroll_settings(payload: PayrollSettings, db: Db, _: CanWps) -> PayrollSettings:
    return staff_service.save_payroll_settings(db, payload)


@router.get("/employees", response_model=list[EmployeeOut])
def employees(db: Db, principal: CanView) -> list[EmployeeOut]:
    return staff_service.employees(db, home_store_id=_home(principal))


@router.get("/employees/{user_id}", response_model=EmployeeOut)
def employee(user_id: uuid.UUID, db: Db, principal: CanView) -> EmployeeOut:
    return staff_service.employee_detail(
        db, user_id, reveal_bank=_sees_bank(principal), home_store_id=_home(principal)
    )


@router.get("/employees/{user_id}/salary-history", response_model=list[SalaryVersionOut])
def salary_history(user_id: uuid.UUID, db: Db, principal: CanView) -> list[SalaryVersionOut]:
    staff_service.employee_detail(db, user_id, reveal_bank=False, home_store_id=_home(principal))
    return staff_service.salary_history(db, user_id)


@router.put("/employees/{user_id}", response_model=list[EmployeeOut])
def save_employee(
    user_id: uuid.UUID, payload: EmployeeProfileWrite, db: Db, principal: CanProfiles
) -> list[EmployeeOut]:
    return staff_service.save_profile(
        db, user_id, payload, actor_id=_user(principal), home_store_id=_home(principal)
    )


@router.get("/payroll/runs", response_model=list[PayrollRunOut])
def runs(db: Db, principal: CanView) -> list[PayrollRunOut]:
    return staff_service.list_runs(db, home_store_id=_home(principal))


@router.post("/payroll/runs", response_model=PayrollRunOut, status_code=201)
def create_run(payload: PayrollRunCreate, db: Db, principal: CanCalculate) -> PayrollRunOut:
    return staff_service.create_run(
        db, payload.year, payload.month, _user(principal), store_id=payload.store_id, home_store_id=_home(principal)
    )


@router.post("/payroll/runs/{run_id}/calculate", response_model=PayrollRunOut)
@router.post("/payroll/runs/{run_id}/recalculate", response_model=PayrollRunOut)
def recalculate(run_id: uuid.UUID, db: Db, principal: CanCalculate) -> PayrollRunOut:
    return staff_service.recalculate(db, run_id, _user(principal))


@router.put("/payroll/runs/{run_id}/lines/{line_id}", response_model=PayrollRunOut)
def update_line(
    run_id: uuid.UUID, line_id: uuid.UUID, payload: PayrollLineWrite, db: Db, _: CanCalculate
) -> PayrollRunOut:
    return staff_service.update_line(db, run_id, line_id, payload)


@router.post("/payroll/runs/{run_id}/submit", response_model=PayrollRunOut)
def submit_run(run_id: uuid.UUID, db: Db, principal: CanSubmit) -> PayrollRunOut:
    return staff_service.submit_run(db, run_id, _user(principal))


@router.post("/payroll/runs/{run_id}/reject", response_model=PayrollRunOut)
def reject_run(run_id: uuid.UUID, payload: PayrollNote, db: Db, principal: CanApprove) -> PayrollRunOut:
    return staff_service.reject_run(db, run_id, _user(principal), payload.note)


@router.post("/payroll/runs/{run_id}/return", response_model=PayrollRunOut)
def return_run(run_id: uuid.UUID, payload: PayrollNote, db: Db, principal: CanApprove) -> PayrollRunOut:
    return staff_service.return_run(db, run_id, _user(principal), payload.note)


@router.post("/payroll/runs/{run_id}/approve", response_model=PayrollRunOut)
@router.post("/payroll/runs/{run_id}/finalize", response_model=PayrollRunOut)
def finalize(run_id: uuid.UUID, db: Db, principal: CanApprove) -> PayrollRunOut:
    return staff_service.finalize(db, run_id, _user(principal))


@router.post("/payroll/runs/{run_id}/cancel", response_model=PayrollRunOut)
def cancel_run(run_id: uuid.UUID, payload: PayrollNote, db: Db, principal: CanCalculate) -> PayrollRunOut:
    return staff_service.cancel_run(db, run_id, _user(principal), payload.note)


@router.post("/payroll/runs/{run_id}/wps/validate", response_model=WpsValidation)
def validate_wps(run_id: uuid.UUID, db: Db, _: CanWps) -> WpsValidation:
    return staff_service.validate_wps(db, run_id)


@router.get("/payroll/runs/{run_id}/wps.sif", response_class=Response)
def wps(run_id: uuid.UUID, db: Db, principal: CanWps) -> Response:
    name, body = staff_service.wps_file(db, run_id, actor_id=_user(principal))
    return Response(body, media_type="text/plain", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.get("/payroll/runs/{run_id}/payments", response_model=list[PayrollPaymentOut])
def payments(run_id: uuid.UUID, db: Db, _: CanView) -> list[PayrollPaymentOut]:
    return staff_service.list_payments(db, run_id)


@router.post("/payroll/runs/{run_id}/payments", response_model=list[PayrollPaymentOut], status_code=201)
def record_payment(
    run_id: uuid.UUID, payload: PayrollPaymentWrite, db: Db, principal: CanPay
) -> list[PayrollPaymentOut]:
    return staff_service.record_payment(db, run_id, payload, _user(principal))


@router.get("/payroll/employees/{user_id}/payslips", response_model=list[PayslipSummary])
def employee_payslips(user_id: uuid.UUID, db: Db, principal: PortalUser) -> list[PayslipSummary]:
    if principal.kind != "user" or principal.scope != "portal":
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    if not _can_read_pay(principal, user_id):
        raise ApiError(403, "forbidden", "You do not have permission for this action.")
    return staff_service.payslips_for(db, user_id)


@router.get("/payroll/payslips/{line_id}.pdf", response_class=Response)
def payslip_pdf(line_id: uuid.UUID, db: Db, principal: PortalUser) -> Response:
    if principal.kind != "user" or principal.scope != "portal":
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    line, run, employee = staff_service._payroll().payslip_source(db, line_id)
    if not _can_read_pay(principal, employee.id):
        raise ApiError(403, "forbidden", "You do not have permission for this action.")
    home = _home(principal)
    own_slip = principal.user is not None and principal.user.id == employee.id
    if home is not None and not own_slip and employee.store_id != home:
        raise ApiError(403, "forbidden", "You can open payslips only for your branch.")
    name, body = payroll_payslip.render(db, line, run, employee)
    return Response(body, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}"'})
