"""Monthly payroll on top of the existing employee profiles, approved timesheets, and commission rules.

Money is integer cents. Salary edits append an effective-dated version and do not rewrite an approved run.
The IBAN is encrypted at rest. A WPS file is an EDR/SCR export, not a payment and not a MOHRE receipt.
"""

from __future__ import annotations

import calendar
import re
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.security import decrypt_value, encrypt_value
from app.models.staff import (
    EmployeeProfile,
    EmployeeSalaryVersion,
    PayrollApproval,
    PayrollLine,
    PayrollPayment,
    PayrollRun,
    PayrollWpsExport,
)
from app.models.store import Store
from app.models.time_entry import TimeEntry
from app.models.user import User
from app.schemas.staff import (
    EmployeeOut,
    EmployeeProfileOut,
    EmployeeProfileWrite,
    PayComponent,
    PayrollExceptionOut,
    PayrollLineOut,
    PayrollLineWrite,
    PayrollPaymentOut,
    PayrollPaymentWrite,
    PayrollRunOut,
    PayrollSettings,
    PayslipSummary,
    SalaryComponent,
    SalaryVersionOut,
    WpsIssue,
    WpsValidation,
)
from app.services import audit, timesheet_service
from app.services.settings_service import business_currency, load_settings

# A blank effective date means the salary already applied before any payroll this product runs.
OPEN_START = date(2000, 1, 1)
FAR_END = date(9999, 12, 31)
FORMULA = (
    "Gross earnings = basic salary + allowances + approved overtime + commission + other earnings. "
    "Net payable = gross earnings - total deductions."
)
WPS_PROVIDER = "uae_sif_edr_scr"
WPS_NOTE = (
    "This file uses the Salary Information File layout already produced by AxizPOS: one EDR row per employee "
    "and an SCR control row. It is not a MOHRE submission receipt and it does not confirm that the bank paid "
    "the salaries. Confirm the file with the salary bank before uploading it."
)
STANDARD_FIELDS = {
    "HOUSING": "housing_allowance_cents",
    "TRANSPORT": "transport_allowance_cents",
    "FOOD": "food_allowance_cents",
    "OTHER": "other_allowance_cents",
    "VARIABLE": "variable_allowance_cents",
    "RECURRING": "recurring_deduction_cents",
}
STANDARD_CODES = set(STANDARD_FIELDS)
MUTABLE = {"DRAFT"}
APPROVABLE = {"DRAFT", "UNDER_REVIEW"}
PAYABLE = {"FINALIZED"}


def cents_text(cents: int) -> str:
    """Two decimal places without binary floating point."""
    sign = "-" if cents < 0 else ""
    amount = abs(int(cents))
    return f"{sign}{amount // 100}.{amount % 100:02d}"


def _mask_id(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        return ""
    if len(cleaned) <= 4:
        return "••••"
    return f"••••{cleaned[-4:]}"


def mask_iban(iban: str) -> str:
    if len(iban) < 8:
        return ""
    return f"{iban[:4]}••••{iban[-4:]}"


def plain_iban(profile: EmployeeProfile) -> str:
    token = profile.iban_encrypted or ""
    if token:
        try:
            return decrypt_value(token, get_settings())
        except Exception:
            return ""
    legacy = (profile.iban or "").replace(" ", "").upper()
    if legacy.startswith("AE") and len(legacy) == 23 and legacy[2:].isdigit():
        return legacy
    return ""


def _store_iban(profile: EmployeeProfile, plain: str) -> None:
    if not plain:
        profile.iban_encrypted = ""
        profile.iban_last4 = ""
        profile.iban = ""
        return
    profile.iban_encrypted = encrypt_value(plain, get_settings())
    profile.iban_last4 = plain[-4:]
    profile.iban = ""


def _snapshot(profile: EmployeeProfile) -> dict[str, object]:
    return {
        "basic_salary_cents": profile.basic_salary_cents,
        "housing_allowance_cents": profile.housing_allowance_cents,
        "transport_allowance_cents": profile.transport_allowance_cents,
        "food_allowance_cents": profile.food_allowance_cents,
        "other_allowance_cents": profile.other_allowance_cents,
        "variable_allowance_cents": profile.variable_allowance_cents,
        "recurring_deduction_cents": profile.recurring_deduction_cents,
        "overtime_rate_pct": profile.overtime_rate_pct,
        "overtime_eligible": profile.overtime_eligible,
        "commission_eligible": profile.commission_eligible,
        "components": list(profile.components or []),
    }


def _int(data: dict[str, object], key: str) -> int:
    try:
        return int(data.get(key) or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


def _custom(data: dict[str, object], kind: str) -> int:
    total = 0
    for row in data.get("components") or []:  # type: ignore[union-attr]
        if not isinstance(row, dict) or not row.get("active", True):
            continue
        if str(row.get("code") or "") in STANDARD_CODES:
            continue
        if row.get("kind") != kind:
            continue
        try:
            total += int(row.get("amount_cents") or 0)
        except (TypeError, ValueError):
            continue
    return total


def payroll_settings(db: Session) -> PayrollSettings | None:
    raw = load_settings(db).payroll
    return PayrollSettings(**raw) if raw else None


def save_payroll_settings(db: Session, data: PayrollSettings) -> PayrollSettings:
    load_settings(db).payroll = data.model_dump()
    audit.record(
        db,
        action_type="UPDATE",
        action="payroll.settings",
        target_entity="BusinessSettings",
        details={"employer_reference": data.employer_reference, "segregate_approval": data.segregate_approval},
    )
    db.commit()
    return data


def _components_out(raw: list | None) -> list[SalaryComponent]:
    found: list[SalaryComponent] = []
    for row in raw or []:
        if not isinstance(row, dict):
            continue
        try:
            found.append(SalaryComponent.model_validate(row))
        except ValueError:
            continue
    return found


def _profile_out(profile: EmployeeProfile, *, reveal: bool) -> EmployeeProfileOut:
    iban = plain_iban(profile)
    labour = profile.labour_id or ""
    routing = profile.bank_routing_code or ""
    return EmployeeProfileOut(
        employee_code=profile.employee_code,
        labour_id=labour if reveal else _mask_id(labour),
        bank_routing_code=routing if reveal else _mask_id(routing),
        iban=iban if reveal else mask_iban(iban),
        iban_masked=not reveal,
        bank_name=profile.bank_name or "",
        account_holder=profile.account_holder if reveal else "",
        job_title=profile.job_title or "",
        nationality=profile.nationality or "",
        phone=profile.phone or "",
        emirates_id=profile.emirates_id if reveal else _mask_id(profile.emirates_id or ""),
        passport_number=profile.passport_number if reveal else _mask_id(profile.passport_number or ""),
        joined_on=profile.joined_on,
        date_of_birth=profile.date_of_birth,
        employment_type=profile.employment_type or "",
        basic_salary_cents=profile.basic_salary_cents,
        housing_allowance_cents=profile.housing_allowance_cents,
        transport_allowance_cents=profile.transport_allowance_cents,
        food_allowance_cents=profile.food_allowance_cents,
        other_allowance_cents=profile.other_allowance_cents,
        variable_allowance_cents=profile.variable_allowance_cents,
        recurring_deduction_cents=profile.recurring_deduction_cents,
        components=_components_out(profile.components),
        overtime_rate_pct=profile.overtime_rate_pct,
        overtime_eligible=profile.overtime_eligible,
        commission_eligible=profile.commission_eligible,
        salary_frequency="MONTHLY",
        profile_status=profile.profile_status if profile.profile_status in {"DRAFT", "ACTIVE"} else "ACTIVE",  # type: ignore[arg-type]
        effective_from=profile.effective_from,
        is_active=profile.is_active,
    )


def _version_out(row: EmployeeSalaryVersion) -> SalaryVersionOut:
    snap = row.snapshot or {}
    return SalaryVersionOut(
        id=row.id,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        status=row.status,
        basic_salary_cents=_int(snap, "basic_salary_cents"),
        housing_allowance_cents=_int(snap, "housing_allowance_cents"),
        transport_allowance_cents=_int(snap, "transport_allowance_cents"),
        food_allowance_cents=_int(snap, "food_allowance_cents"),
        other_allowance_cents=_int(snap, "other_allowance_cents"),
        variable_allowance_cents=_int(snap, "variable_allowance_cents"),
        recurring_deduction_cents=_int(snap, "recurring_deduction_cents"),
        overtime_rate_pct=_int(snap, "overtime_rate_pct") or 125,
        overtime_eligible=bool(snap.get("overtime_eligible", True)),
        commission_eligible=bool(snap.get("commission_eligible", True)),
    )


def _next_employee_code(db: Session) -> str:
    highest = 0
    for code in db.scalars(select(EmployeeProfile.employee_code)):
        match = re.fullmatch(r"EMP(\d+)", code or "")
        if match:
            highest = max(highest, int(match.group(1)))
    return f"EMP{highest + 1:04d}"


def _in_branch(user: User, home_store_id: uuid.UUID | None) -> bool:
    return home_store_id is None or user.store_id == home_store_id


def employees(
    db: Session,
    *,
    reveal_bank: bool = False,
    home_store_id: uuid.UUID | None = None,
    only_user_id: uuid.UUID | None = None,
) -> list[EmployeeOut]:
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    stores = {row.id: row.name for row in db.scalars(select(Store))}
    out: list[EmployeeOut] = []
    for user in db.scalars(select(User).order_by(User.full_name)).unique():
        if only_user_id is not None and user.id != only_user_id:
            continue
        if not _in_branch(user, home_store_id):
            continue
        profile = profiles.get(user.id)
        if not user.is_active and profile is None:
            continue
        out.append(
            EmployeeOut(
                user_id=user.id,
                name=user.full_name,
                role_name=user.role.name if user.role else "",
                store_id=user.store_id,
                store_name=stores.get(user.store_id, "") if user.store_id else "",
                employment_status="ACTIVE" if user.is_active else "INACTIVE",
                profile=_profile_out(profile, reveal=reveal_bank) if profile else None,
            )
        )
    return out


def employee_detail(
    db: Session,
    user_id: uuid.UUID,
    *,
    reveal_bank: bool,
    home_store_id: uuid.UUID | None = None,
) -> EmployeeOut:
    found = employees(db, reveal_bank=reveal_bank, home_store_id=home_store_id, only_user_id=user_id)
    if not found:
        raise ApiError(404, "not_found", "That person was not found.")
    found[0].salary_history = salary_history(db, user_id)
    return found[0]


def salary_history(db: Session, user_id: uuid.UUID) -> list[SalaryVersionOut]:
    profile = db.scalar(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
    if profile is None:
        return []
    rows = db.scalars(
        select(EmployeeSalaryVersion)
        .where(EmployeeSalaryVersion.profile_id == profile.id)
        .order_by(EmployeeSalaryVersion.effective_from.desc())
    )
    return [_version_out(row) for row in rows]


def _finalized_periods(db: Session, user_id: uuid.UUID) -> list[tuple[date, date]]:
    runs = db.scalars(
        select(PayrollRun)
        .join(PayrollLine, PayrollLine.run_id == PayrollRun.id)
        .where(PayrollLine.user_id == user_id, PayrollRun.status == "FINALIZED")
    ).unique()
    return [_period(run) for run in runs]


def _overlaps(start: date, end: date | None, period_start: date, period_end: date) -> bool:
    return start <= period_end and (end or FAR_END) >= period_start


def _locked(db: Session, user_id: uuid.UUID, start: date, end: date | None) -> bool:
    periods = _finalized_periods(db, user_id)
    return any(_overlaps(start, end, period_start, period_end) for period_start, period_end in periods)


def _record_version(
    db: Session, profile: EmployeeProfile, effective_from: date | None, actor_id: uuid.UUID | None
) -> None:
    start = effective_from or OPEN_START
    versions = list(
        db.scalars(
            select(EmployeeSalaryVersion)
            .where(EmployeeSalaryVersion.profile_id == profile.id)
            .order_by(EmployeeSalaryVersion.effective_from)
        )
    )
    status = "DRAFT" if profile.profile_status == "DRAFT" else "ACTIVE"
    same = next((row for row in versions if row.effective_from == start), None)
    if same is not None:
        if _locked(db, profile.user_id, same.effective_from, same.effective_to):
            raise ApiError(
                409,
                "salary_locked",
                "An approved payroll already uses this salary period. Choose a later effective date.",
            )
        same.snapshot = _snapshot(profile)
        same.status = status if same.effective_to is None else "SUPERSEDED"
        same.created_by_id = actor_id
        return
    if _locked(db, profile.user_id, start, None):
        raise ApiError(
            409,
            "salary_locked",
            "That effective date overlaps an approved payroll. Choose a date after that payroll.",
        )
    for row in versions:
        row_end = row.effective_to or FAR_END
        if row.effective_from < start <= row_end:
            row.effective_to = start - timedelta(days=1)
            row.status = "SUPERSEDED"
        elif row.effective_from >= start:
            raise ApiError(409, "salary_overlap", "Salary periods cannot overlap. Choose a later effective date.")
    db.add(
        EmployeeSalaryVersion(
            profile_id=profile.id,
            effective_from=start,
            effective_to=None,
            status=status,
            snapshot=_snapshot(profile),
            created_by_id=actor_id,
        )
    )


def save_profile(
    db: Session,
    user_id: uuid.UUID,
    data: EmployeeProfileWrite,
    *,
    actor_id: uuid.UUID | None = None,
    home_store_id: uuid.UUID | None = None,
) -> list[EmployeeOut]:
    user = db.get(User, user_id)
    if user is None or not _in_branch(user, home_store_id):
        raise ApiError(404, "not_found", "That person was not found.")
    profile = db.scalar(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
    if profile is None:
        profile = EmployeeProfile(user_id=user_id, employee_code=_next_employee_code(db), basic_salary_cents=0)
        db.add(profile)
    skip = {"components", "effective_from", "profile_status", "iban", "is_active"}
    for key, value in data.model_dump(exclude=skip).items():
        setattr(profile, key, value)
    profile.components = [row.model_dump() for row in data.components]
    for row in data.components:
        field = STANDARD_FIELDS.get(row.code)
        if field and row.active:
            setattr(profile, field, row.amount_cents)
    profile.profile_status = data.profile_status
    profile.is_active = bool(data.is_active and data.profile_status == "ACTIVE")
    profile.effective_from = data.effective_from
    _store_iban(profile, data.iban)
    db.flush()
    _record_version(db, profile, data.effective_from, actor_id)
    audit.record(
        db,
        action_type="UPDATE",
        action="payroll.profile",
        target_entity="EmployeeProfile",
        target_entity_id=profile.id,
        user_id=actor_id,
        details={
            "employee_code": profile.employee_code,
            "employee_user_id": str(user_id),
            "profile_status": profile.profile_status,
            "effective_from": data.effective_from.isoformat() if data.effective_from else None,
            "iban_last4": profile.iban_last4,
        },
    )
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "salary_overlap", "Salary periods cannot overlap. Choose a later effective date.") from None
    return employees(db, home_store_id=home_store_id)


def _period(run: PayrollRun) -> tuple[date, date]:
    return date(run.year, run.month, 1), date(run.year, run.month, calendar.monthrange(run.year, run.month)[1])


def _leave_deduction(line: PayrollLine) -> int:
    return (line.basic_cents + line.allowances_cents) * line.unpaid_leave_days // 30


def _gross(line: PayrollLine) -> int:
    return line.basic_cents + line.allowances_cents + line.overtime_cents + line.commission_cents + line.bonus_cents


def _deductions(line: PayrollLine) -> int:
    return line.deductions_cents + line.recurring_deduction_cents + _leave_deduction(line)


def _net(line: PayrollLine) -> int:
    return _gross(line) - _deductions(line)


def _overtime_pay(basic: int, minutes: int, rate: int, eligible: bool) -> int:
    if not eligible or minutes <= 0 or basic <= 0:
        return 0
    return basic * minutes * rate // (30 * 8 * 60 * 100)


def _covering(versions: list[EmployeeSalaryVersion], start: date, end: date) -> EmployeeSalaryVersion | None:
    best: EmployeeSalaryVersion | None = None
    for row in versions:
        if row.status == "DRAFT":
            continue
        if row.effective_from > end:
            continue
        if row.effective_to is not None and row.effective_to < start:
            continue
        if best is None or row.effective_from > best.effective_from:
            best = row
    return best


def _amounts_for(profile: EmployeeProfile, version: EmployeeSalaryVersion | None) -> dict[str, object]:
    if version is None:
        return _snapshot(profile)
    data = dict(version.snapshot or {})
    data.setdefault("components", [])
    return data


def _component_rows(line: PayrollLine, amounts: dict[str, object]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    def add(name: str, kind: str, cents: int, source: str) -> None:
        if cents:
            rows.append({"name": name, "kind": kind, "cents": int(cents), "source": source})

    add("Basic salary", "EARNING", line.basic_cents, "Salary profile")
    add("Housing allowance", "EARNING", _int(amounts, "housing_allowance_cents"), "Salary profile")
    add("Transport allowance", "EARNING", _int(amounts, "transport_allowance_cents"), "Salary profile")
    add("Food allowance", "EARNING", _int(amounts, "food_allowance_cents"), "Salary profile")
    add("Other allowances", "EARNING", _int(amounts, "other_allowance_cents"), "Salary profile")
    add("Variable allowance", "EARNING", _int(amounts, "variable_allowance_cents"), "Salary profile")
    for row in amounts.get("components") or []:  # type: ignore[union-attr]
        if not isinstance(row, dict) or not row.get("active", True):
            continue
        if str(row.get("code") or "") in STANDARD_CODES:
            continue
        kind = "EARNING" if row.get("kind") == "ALLOWANCE" else "DEDUCTION"
        try:
            cents = int(row.get("amount_cents") or 0)
        except (TypeError, ValueError):
            cents = 0
        add(str(row.get("name") or "Adjustment"), kind, cents, "Salary profile")
    add("Approved overtime", "EARNING", line.overtime_cents, "Approved timesheets")
    add("Commission", "EARNING", line.commission_cents, "Posted sales under active commission rules")
    add("Other earnings", "EARNING", line.bonus_cents, "Payroll adjustment")
    add("Recurring deductions", "DEDUCTION", _int(amounts, "recurring_deduction_cents"), "Salary profile")
    add("Deductions", "DEDUCTION", line.deductions_cents, "Payroll adjustment")
    add("Unpaid leave", "DEDUCTION", _leave_deduction(line), "Payroll adjustment")
    return rows


def _stamp(line: PayrollLine, version_id: uuid.UUID | None, amounts: dict[str, object]) -> None:
    line.gross_cents = _gross(line)
    line.net_cents = _net(line)
    line.breakdown = {
        "version_id": str(version_id) if version_id else None,
        "formula": FORMULA,
        "components": _component_rows(line, amounts),
        "amounts": {key: value for key, value in amounts.items() if key != "components"},
    }


def _apply_pay(
    line: PayrollLine,
    amounts: dict[str, object],
    *,
    overtime_minutes: int,
    commission_cents: int,
    version_id: uuid.UUID | None,
) -> None:
    basic = _int(amounts, "basic_salary_cents")
    rate = _int(amounts, "overtime_rate_pct") or 125
    eligible = bool(amounts.get("overtime_eligible", True))
    line.basic_cents = basic
    line.variable_cents = _int(amounts, "variable_allowance_cents")
    line.allowances_cents = (
        _int(amounts, "housing_allowance_cents")
        + _int(amounts, "transport_allowance_cents")
        + _int(amounts, "food_allowance_cents")
        + _int(amounts, "other_allowance_cents")
        + line.variable_cents
        + _custom(amounts, "ALLOWANCE")
    )
    line.overtime_minutes = overtime_minutes
    line.overtime_cents = _overtime_pay(basic, overtime_minutes, rate, eligible)
    line.commission_cents = commission_cents if bool(amounts.get("commission_eligible", True)) else 0
    line.recurring_deduction_cents = _int(amounts, "recurring_deduction_cents") + _custom(amounts, "DEDUCTION")
    line.bonus_cents = line.bonus_cents or 0
    line.deductions_cents = line.deductions_cents or 0
    line.unpaid_leave_days = line.unpaid_leave_days or 0
    _stamp(line, version_id, amounts)


def _exclusion(
    profile: EmployeeProfile | None,
    user: User,
    version: EmployeeSalaryVersion | None,
    versions: list[EmployeeSalaryVersion],
    start: date,
    end: date,
) -> str | None:
    if not user.is_active:
        return "inactive_employee"
    if profile is None:
        return "no_profile"
    if profile.profile_status == "DRAFT":
        return "draft_profile"
    if not profile.is_active:
        return "inactive_profile"
    if profile.joined_on is not None and profile.joined_on > end:
        return "joined_after"
    if versions and version is None:
        return "effective_date"
    if version is None and profile.effective_from is not None and profile.effective_from > end:
        return "effective_date"
    return None


_EXCLUSION_TEXT = {
    "inactive_employee": "Inactive employee.",
    "no_profile": "No salary profile.",
    "draft_profile": "Salary profile is still a draft.",
    "inactive_profile": "Salary profile is inactive.",
    "joined_after": "Joined after this payroll period.",
    "effective_date": "No salary version covers this payroll period.",
}


def _fill(db: Session, run: PayrollRun) -> None:
    from app.services.staff_service import commissions

    start, end = _period(run)
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    report = commissions(db, start=start, end=end, store_id=run.store_id)
    earned = {row.user_id: row.commission_cents for row in report.staff}
    pending = {
        user_id: count
        for user_id, count in db.execute(
            select(TimeEntry.user_id, func.count())
            .where(TimeEntry.status == "CLOSED", TimeEntry.clock_in_at >= since, TimeEntry.clock_in_at < until)
            .group_by(TimeEntry.user_id)
        )
    }
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    versions: dict[uuid.UUID, list[EmployeeSalaryVersion]] = defaultdict(list)
    for row in db.scalars(select(EmployeeSalaryVersion)):
        versions[row.profile_id].append(row)
    existing = {line.user_id: line for line in run.lines}
    included: set[uuid.UUID] = set()
    exceptions: list[dict[str, object]] = []
    warned: set[uuid.UUID] = set()

    def flag(user: User, severity: str, code: str, message: str) -> None:
        exceptions.append(
            {"user_id": str(user.id), "name": user.full_name, "severity": severity, "code": code, "message": message}
        )
        if severity == "WARNING":
            warned.add(user.id)

    for user in db.scalars(select(User).order_by(User.full_name)).unique():
        if run.store_id is not None and user.store_id != run.store_id:
            continue
        profile = profiles.get(user.id)
        if not user.is_active and profile is None:
            continue
        history = versions.get(profile.id, []) if profile is not None else []
        version = _covering(history, start, end) if profile is not None else None
        reason = _exclusion(profile, user, version, history, start, end)
        if reason is not None:
            flag(user, "EXCLUDED", reason, _EXCLUSION_TEXT[reason])
            continue
        assert profile is not None
        amounts = _amounts_for(profile, version)
        _, overtime_minutes = timesheet_service.approved_minutes(db, user_id=user.id, start=start, end=end)
        if pending.get(user.id):
            flag(user, "WARNING", "unapproved_timesheet", "Unapproved timesheet hours were left out.")
        if profile.joined_on is not None and start <= profile.joined_on <= end:
            flag(user, "WARNING", "joined_during", "Joined during the month. Pay is the full monthly salary.")
        if overtime_minutes and not bool(amounts.get("overtime_eligible", True)):
            flag(
                user,
                "WARNING",
                "overtime_ineligible",
                "Approved overtime was not paid. This profile is not eligible.",
            )
        if earned.get(user.id, 0) and not bool(amounts.get("commission_eligible", True)):
            flag(user, "WARNING", "commission_ineligible", "Commission was left out. This profile is not eligible.")
        line = existing.get(user.id)
        if line is None:
            line = PayrollLine(
                user_id=user.id, employee_code=profile.employee_code, basic_cents=0, allowances_cents=0, net_cents=0
            )
            run.lines.append(line)
        line.employee_code = profile.employee_code
        commission_cents = earned.get(user.id, 0)
        _apply_pay(
            line,
            amounts,
            overtime_minutes=overtime_minutes,
            commission_cents=commission_cents,
            version_id=version.id if version is not None else None,
        )
        line.calculation_status = "WARNING" if user.id in warned else "OK"
        included.add(user.id)
    for line in list(run.lines):
        if line.user_id not in included:
            run.lines.remove(line)
    run.exceptions = exceptions


def _aware(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _components_from(line: PayrollLine) -> list[PayComponent]:
    raw = (line.breakdown or {}).get("components") or []
    found: list[PayComponent] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        kind = row.get("kind")
        if kind not in {"EARNING", "DEDUCTION"}:
            continue
        found.append(
            PayComponent(
                name=str(row.get("name") or ""),
                kind=kind,
                cents=int(row.get("cents") or 0),
                source=str(row.get("source") or ""),
            )
        )
    return found


def _run_out(db: Session, run: PayrollRun) -> PayrollRunOut:
    user_ids = [line.user_id for line in run.lines]
    users = (
        {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).unique()} if user_ids else {}
    )
    stores = {row.id: row.name for row in db.scalars(select(Store))}
    exceptions = []
    for row in run.exceptions or []:
        if isinstance(row, dict):
            try:
                exceptions.append(PayrollExceptionOut.model_validate(row))
            except ValueError:
                continue
    return PayrollRunOut(
        id=run.id,
        year=run.year,
        month=run.month,
        status=run.status,  # type: ignore[arg-type]
        payment_status=run.payment_status if run.payment_status else "NONE",  # type: ignore[arg-type]
        store_id=run.store_id,
        currency=run.currency,
        finalized_at=_aware(run.finalized_at),
        total_gross_cents=sum(_gross(line) for line in run.lines),
        total_deductions_cents=sum(_deductions(line) for line in run.lines),
        total_net_cents=sum(line.net_cents for line in run.lines),
        exceptions=exceptions,
        lines=[
            PayrollLineOut(
                id=line.id,
                user_id=line.user_id,
                name=users[line.user_id].full_name if line.user_id in users else "",
                employee_code=line.employee_code,
                store_id=users[line.user_id].store_id if line.user_id in users else None,
                store_name=(
                    stores.get(users[line.user_id].store_id, "")
                    if line.user_id in users and users[line.user_id].store_id
                    else ""
                ),
                basic_cents=line.basic_cents,
                allowances_cents=line.allowances_cents,
                overtime_minutes=line.overtime_minutes,
                overtime_cents=line.overtime_cents,
                commission_cents=line.commission_cents,
                bonus_cents=line.bonus_cents,
                deductions_cents=line.deductions_cents,
                recurring_deduction_cents=line.recurring_deduction_cents,
                unpaid_leave_days=line.unpaid_leave_days,
                leave_deduction_cents=_leave_deduction(line),
                gross_cents=_gross(line),
                note=line.note,
                net_cents=line.net_cents,
                calculation_status=line.calculation_status or "OK",
                components=_components_from(line),
                formula=str((line.breakdown or {}).get("formula") or FORMULA),
            )
            for line in run.lines
        ],
    )


def _run(db: Session, run_id: uuid.UUID) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Payroll run was not found.")
    return run


def _event(db: Session, run: PayrollRun, action: str, actor_id: uuid.UUID | None, note: str = "") -> None:
    db.add(PayrollApproval(run_id=run.id, action=action, actor_id=actor_id, note=note[:255]))
    audit.record(
        db,
        action_type="UPDATE",
        action=f"payroll.{action.lower()}",
        target_entity="PayrollRun",
        target_entity_id=run.id,
        user_id=actor_id,
        details={"year": run.year, "month": run.month, "status": run.status, "note": note[:255]},
    )


def _overlaps_scope(existing: PayrollRun, store_id: uuid.UUID | None) -> bool:
    if store_id is None or existing.store_id is None:
        return True
    return existing.store_id == store_id


def list_runs(db: Session, *, home_store_id: uuid.UUID | None = None) -> list[PayrollRunOut]:
    statement = select(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    if home_store_id is not None:
        statement = statement.where(PayrollRun.store_id == home_store_id)
    return [_run_out(db, run) for run in db.scalars(statement)]


def create_run(
    db: Session,
    year: int,
    month: int,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None = None,
    home_store_id: uuid.UUID | None = None,
) -> PayrollRunOut:
    if home_store_id is not None:
        if store_id is not None and store_id != home_store_id:
            raise ApiError(403, "forbidden", "You can run payroll only for your branch.")
        store_id = home_store_id
    if store_id is not None and db.get(Store, store_id) is None:
        raise ApiError(404, "not_found", "That branch was not found.")
    open_runs = list(
        db.scalars(
            select(PayrollRun).where(
                PayrollRun.year == year, PayrollRun.month == month, PayrollRun.status != "CANCELLED"
            )
        )
    )
    if any(_overlaps_scope(existing, store_id) for existing in open_runs):
        raise ApiError(409, "run_exists", f"Payroll for {calendar.month_name[month]} {year} already exists.")
    run = PayrollRun(
        year=year,
        month=month,
        store_id=store_id,
        currency=business_currency(db),
        created_by_id=user_id,
        payment_status="NONE",
    )
    db.add(run)
    db.flush()
    _fill(db, run)
    if not run.lines:
        reasons = "; ".join(str(row.get("message")) for row in (run.exceptions or [])[:5] if isinstance(row, dict))
        db.rollback()
        raise ApiError(422, "no_employees", reasons or "Add payroll details for at least one employee first.")
    _event(db, run, "CALCULATE", user_id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "run_exists", f"Payroll for {calendar.month_name[month]} {year} already exists.") from None
    return _run_out(db, run)


def recalculate(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status not in MUTABLE:
        raise ApiError(409, "run_final", "A payroll can only be recalculated while it is a draft.")
    _fill(db, run)
    if not run.lines:
        db.rollback()
        raise ApiError(422, "no_employees", "Add payroll details for at least one employee first.")
    _event(db, run, "CALCULATE", actor_id)
    db.commit()
    return _run_out(db, run)


def update_line(db: Session, run_id: uuid.UUID, line_id: uuid.UUID, data: PayrollLineWrite) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status not in MUTABLE:
        raise ApiError(409, "run_final", "A finalized payroll cannot change.")
    line = next((row for row in run.lines if row.id == line_id), None)
    if line is None:
        raise ApiError(404, "not_found", "Payroll line was not found.")
    line.bonus_cents = data.bonus_cents
    line.deductions_cents = data.deductions_cents
    line.unpaid_leave_days = data.unpaid_leave_days
    line.note = data.note.strip()
    amounts = dict((line.breakdown or {}).get("amounts") or {})
    version_raw = (line.breakdown or {}).get("version_id")
    version_id = uuid.UUID(version_raw) if isinstance(version_raw, str) else None
    _stamp(line, version_id, amounts)
    if line.net_cents < 0:
        db.rollback()
        raise ApiError(422, "negative_pay", "Deductions cannot exceed the month's pay.")
    db.commit()
    return _run_out(db, run)


def submit_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status != "DRAFT":
        raise ApiError(409, "run_state", "Only a draft payroll can be submitted for review.")
    if not run.lines:
        raise ApiError(422, "no_employees", "This payroll has no employees.")
    run.status = "UNDER_REVIEW"
    run.submitted_by_id = actor_id
    run.submitted_at = datetime.now(UTC)
    _event(db, run, "SUBMIT", actor_id)
    db.commit()
    return _run_out(db, run)


def _return_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str, action: str) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status != "UNDER_REVIEW":
        raise ApiError(409, "run_state", "Only a payroll that is under review can be sent back.")
    cleaned = audit.require_reason(note, "sending a payroll back")
    run.status = "DRAFT"
    run.rejection_note = cleaned[:255]
    _event(db, run, action, actor_id, cleaned)
    db.commit()
    return _run_out(db, run)


def reject_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str) -> PayrollRunOut:
    return _return_run(db, run_id, actor_id, note, "REJECT")


def return_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str) -> PayrollRunOut:
    return _return_run(db, run_id, actor_id, note, "RETURN")


def finalize(db: Session, run_id: uuid.UUID, user_id: uuid.UUID | None) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status == "FINALIZED":
        raise ApiError(409, "run_final", "This payroll is already finalized.")
    if run.status not in APPROVABLE:
        raise ApiError(409, "run_state", "This payroll cannot be approved.")
    if any(line.net_cents < 0 for line in run.lines):
        raise ApiError(422, "negative_pay", "Deductions cannot exceed the month's pay.")
    settings = payroll_settings(db)
    if settings and settings.segregate_approval and user_id is not None and run.created_by_id == user_id:
        raise ApiError(403, "segregation", "The person who prepared this payroll cannot approve it.")
    run.status = "FINALIZED"
    run.finalized_by_id = user_id
    run.finalized_at = datetime.now(UTC)
    _event(db, run, "APPROVE", user_id)
    db.commit()
    return _run_out(db, run)


def cancel_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str = "") -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status not in {"DRAFT", "UNDER_REVIEW"}:
        raise ApiError(409, "run_state", "An approved payroll cannot be cancelled. Record an adjustment instead.")
    run.status = "CANCELLED"
    run.rejection_note = note.strip()[:255]
    _event(db, run, "CANCEL", actor_id, note.strip())
    db.commit()
    return _run_out(db, run)


def _issue(line: PayrollLine, name: str, code: str, message: str) -> WpsIssue:
    return WpsIssue(user_id=line.user_id, employee_code=line.employee_code, name=name, code=code, message=message)


def _wps_issues(db: Session, run: PayrollRun) -> list[WpsIssue]:
    issues: list[WpsIssue] = []
    if run.status != "FINALIZED":
        issues.append(WpsIssue(code="not_approved", message="Approve the payroll before generating the WPS file."))
    if payroll_settings(db) is None:
        issues.append(
            WpsIssue(
                code="employer",
                message="Enter the employer's MOHRE establishment ID and bank routing code first.",
            )
        )
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    user_ids = [line.user_id for line in run.lines]
    users = (
        {user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).unique()} if user_ids else {}
    )
    for line in run.lines:
        profile = profiles.get(line.user_id)
        user = users.get(line.user_id)
        name = user.full_name if user is not None else ""
        if profile is None:
            issues.append(_issue(line, name, "no_profile", "Salary profile is missing."))
            continue
        if user is not None and not user.is_active:
            issues.append(_issue(line, name, "inactive", "Employee is inactive."))
        if not profile.is_active or profile.profile_status != "ACTIVE":
            issues.append(_issue(line, name, "inactive", "Salary profile is inactive."))
        if line.net_cents <= 0:
            issues.append(_issue(line, name, "net_payable", "Net payable must be greater than zero."))
            continue
        if not re.fullmatch(r"\d{14}", profile.labour_id or ""):
            issues.append(_issue(line, name, "labour_id", "MOHRE personal number is missing."))
        if not re.fullmatch(r"\d{9}", profile.bank_routing_code or ""):
            issues.append(_issue(line, name, "routing", "Employee bank routing code is missing."))
        iban = plain_iban(profile)
        if not iban:
            issues.append(_issue(line, name, "iban", "IBAN is missing."))
        elif not (iban.startswith("AE") and len(iban) == 23 and iban[2:].isdigit()):
            issues.append(_issue(line, name, "iban", "IBAN is not a valid UAE IBAN."))
    return issues


def validate_wps(db: Session, run_id: uuid.UUID) -> WpsValidation:
    run = _run(db, run_id)
    issues = _wps_issues(db, run)
    blocking = [row for row in issues if row.code != "net_payable"]
    # A zero net is reported and left out of the file. It blocks only when nobody else can be paid.
    payable = [line for line in run.lines if line.net_cents > 0]
    ready = run.status == "FINALIZED" and payroll_settings(db) is not None and not blocking and bool(payable)
    return WpsValidation(ready=ready, provider=WPS_PROVIDER, provider_note=WPS_NOTE, issues=issues)


def wps_file(
    db: Session, run_id: uuid.UUID, now: datetime | None = None, actor_id: uuid.UUID | None = None
) -> tuple[str, str]:
    """EDR/SCR salary file. Returns (filename, body). Does not mark the payroll paid."""
    run = _run(db, run_id)
    if run.status != "FINALIZED":
        raise ApiError(409, "run_draft", "Finalize the payroll before exporting the WPS file.")
    employer = payroll_settings(db)
    if employer is None:
        raise ApiError(422, "wps_settings", "Enter the employer's MOHRE establishment ID and bank routing code first.")
    issues = [row for row in _wps_issues(db, run) if row.code not in {"not_approved", "employer", "net_payable"}]
    if issues:
        raise ApiError(422, "wps_invalid", issues[0].message)
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    start, end = _period(run)
    days = (end - start).days + 1
    rows: list[str] = []
    total = 0
    for line in run.lines:
        profile = profiles.get(line.user_id)
        if profile is None or line.net_cents <= 0:
            continue
        variable = line.variable_cents + line.overtime_cents + line.commission_cents + line.bonus_cents
        fixed = line.net_cents - variable
        total += line.net_cents
        rows.append(
            ",".join(
                [
                    "EDR",
                    profile.labour_id,
                    profile.bank_routing_code,
                    plain_iban(profile),
                    start.isoformat(),
                    end.isoformat(),
                    str(days),
                    cents_text(fixed),
                    cents_text(variable),
                    str(line.unpaid_leave_days),
                ]
            )
        )
    if not rows:
        raise ApiError(422, "wps_invalid", "No employee has a positive net payable to export.")
    moment = now or datetime.now(UTC)
    reference = employer.employer_reference or f"SAL{run.year}{run.month:02d}"
    rows.append(
        ",".join(
            [
                "SCR",
                employer.employer_id,
                employer.bank_routing_code,
                moment.strftime("%Y-%m-%d"),
                moment.strftime("%H%M"),
                f"{run.month:02d}{run.year}",
                str(len(rows)),
                cents_text(total),
                run.currency,
                reference[:18],
            ]
        )
    )
    filename = f"{employer.employer_id}{moment:%y%m%d%H%M%S}.SIF"
    if run.payment_status in {"NONE", "GENERATED"}:
        run.payment_status = "GENERATED"
    run.wps_generated_at = moment
    db.add(
        PayrollWpsExport(
            run_id=run.id,
            provider=WPS_PROVIDER,
            filename=filename,
            employee_count=len(rows) - 1,
            total_cents=total,
            created_by_id=actor_id,
        )
    )
    _event(db, run, "WPS", actor_id)
    db.commit()
    return filename, "\r\n".join(rows) + "\r\n"


def list_payments(db: Session, run_id: uuid.UUID) -> list[PayrollPaymentOut]:
    _run(db, run_id)
    rows = db.scalars(select(PayrollPayment).where(PayrollPayment.run_id == run_id).order_by(PayrollPayment.created_at))
    return [
        PayrollPaymentOut(
            id=row.id,
            amount_cents=row.amount_cents,
            reference=row.reference,
            status=row.status,
            note=row.note,
            created_at=_aware(row.created_at) or datetime.now(UTC),
        )
        for row in rows
    ]


def record_payment(
    db: Session, run_id: uuid.UUID, data: PayrollPaymentWrite, actor_id: uuid.UUID | None
) -> list[PayrollPaymentOut]:
    run = _run(db, run_id)
    if run.status not in PAYABLE:
        raise ApiError(409, "run_draft", "Approve the payroll before recording a payment.")
    existing = db.scalar(
        select(PayrollPayment.id).where(PayrollPayment.run_id == run_id, PayrollPayment.reference == data.reference)
    )
    if existing:
        raise ApiError(409, "payment_exists", "This payment reference was already recorded.")
    net = sum(line.net_cents for line in run.lines)
    if net <= 0:
        raise ApiError(422, "net_payable", "This payroll has no positive net payable.")
    db.add(
        PayrollPayment(
            run_id=run.id,
            amount_cents=data.amount_cents,
            reference=data.reference,
            status=data.status,
            note=data.note,
            recorded_by_id=actor_id,
        )
    )
    db.flush()
    paid = sum(
        row.amount_cents
        for row in db.scalars(select(PayrollPayment).where(PayrollPayment.run_id == run_id))
        if row.status in {"PAID", "PARTIALLY_PAID"}
    )
    if data.status in {"PAID", "PARTIALLY_PAID"}:
        run.payment_status = "PAID" if paid >= net else "PARTIALLY_PAID"
    elif run.payment_status not in {"PAID", "PARTIALLY_PAID"}:
        run.payment_status = data.status
    _event(db, run, "PAYMENT", actor_id, data.reference)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise ApiError(409, "payment_exists", "This payment reference was already recorded.") from None
    return list_payments(db, run_id)


def payslips_for(db: Session, user_id: uuid.UUID) -> list[PayslipSummary]:
    rows = db.execute(
        select(PayrollLine, PayrollRun)
        .join(PayrollRun, PayrollRun.id == PayrollLine.run_id)
        .where(PayrollLine.user_id == user_id, PayrollRun.status == "FINALIZED")
        .order_by(PayrollRun.year.desc(), PayrollRun.month.desc())
    )
    return [
        PayslipSummary(
            id=line.id,
            run_id=run.id,
            user_id=line.user_id,
            year=run.year,
            month=run.month,
            currency=run.currency,
            net_cents=line.net_cents,
            payment_status=run.payment_status,
        )
        for line, run in rows
    ]


def payslip_source(db: Session, line_id: uuid.UUID) -> tuple[PayrollLine, PayrollRun, User]:
    line = db.get(PayrollLine, line_id)
    if line is None:
        raise ApiError(404, "not_found", "Payslip was not found.")
    run = _run(db, line.run_id)
    if run.status != "FINALIZED":
        raise ApiError(409, "run_draft", "A payslip is available after the payroll is approved.")
    user = db.get(User, line.user_id)
    if user is None:
        raise ApiError(404, "not_found", "Payslip was not found.")
    return line, run, user


def finalized_in(db: Session, since: datetime, until: datetime) -> list[PayrollRun]:
    return list(
        db.scalars(
            select(PayrollRun).where(
                PayrollRun.status == "FINALIZED",
                PayrollRun.finalized_at >= since,
                PayrollRun.finalized_at < until,
            )
        )
    )
