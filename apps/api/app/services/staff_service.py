"""Sales commissions, employee payroll profiles, monthly payroll runs, and the UAE WPS salary file (SIF)."""

from __future__ import annotations

import calendar
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.staff import CommissionRule, EmployeeProfile, PayrollLine, PayrollRun
from app.models.user import User
from app.schemas.staff import (
    CommissionByRule,
    CommissionReport,
    CommissionRuleOut,
    CommissionRuleWrite,
    EmployeeOut,
    EmployeeProfileWrite,
    PayrollLineOut,
    PayrollLineWrite,
    PayrollRunOut,
    PayrollSettings,
    StaffCommission,
)
from app.services import timesheet_service
from app.services.settings_service import business_currency, load_settings

POSTED = ("completed", "partially_refunded", "refunded")


# --- Commission rules -------------------------------------------------------------------------------------


def _rule_out(rule: CommissionRule) -> CommissionRuleOut:
    return CommissionRuleOut(
        id=rule.id,
        name=rule.name,
        basis=rule.basis,  # type: ignore[arg-type]
        rate_bps=rule.rate_bps,
        category_ids=[uuid.UUID(item) for item in rule.category_ids or []],
        role_ids=[uuid.UUID(item) for item in rule.role_ids or []],
        threshold_cents=rule.threshold_cents,
        is_active=rule.is_active,
    )


def list_rules(db: Session) -> list[CommissionRuleOut]:
    return [_rule_out(rule) for rule in db.scalars(select(CommissionRule).order_by(CommissionRule.name))]


def save_rule(db: Session, data: CommissionRuleWrite, rule_id: uuid.UUID | None = None) -> CommissionRuleOut:
    rule = db.get(CommissionRule, rule_id) if rule_id else CommissionRule()
    if rule is None:
        raise ApiError(404, "not_found", "Commission rule was not found.")
    rule.name = data.name.strip()
    rule.basis = data.basis
    rule.rate_bps = data.rate_bps
    rule.category_ids = [str(item) for item in data.category_ids]
    rule.role_ids = [str(item) for item in data.role_ids]
    rule.threshold_cents = data.threshold_cents
    rule.is_active = data.is_active
    if rule_id is None:
        db.add(rule)
    db.commit()
    return _rule_out(rule)


def _pick(rules: list[CommissionRule], category_id: str | None, role_id: str) -> CommissionRule | None:
    """The most specific active rule for a line: category beats all-products, then role beats all-roles."""
    best: tuple[int, int, CommissionRule] | None = None
    for rule in rules:
        if rule.category_ids and category_id not in rule.category_ids:
            continue
        if rule.role_ids and role_id not in rule.role_ids:
            continue
        score = (2 if rule.category_ids else 0) + (1 if rule.role_ids else 0)
        if best is None or (score, rule.rate_bps) > (best[0], best[1]):
            best = (score, rule.rate_bps, rule)
    return best[2] if best else None


def commissions(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> CommissionReport:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Choose a period of at most 400 days that ends after it starts.")
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    rules = list(db.scalars(select(CommissionRule).where(CommissionRule.is_active.is_(True))))
    users: dict[uuid.UUID, User] = {}

    def person(user_id: uuid.UUID) -> User | None:
        if user_id not in users:
            found = db.get(User, user_id)
            if found is not None:
                users[user_id] = found
        return users.get(user_id)

    basis: dict[tuple[uuid.UUID, uuid.UUID], int] = defaultdict(int)
    lines: dict[uuid.UUID, int] = defaultdict(int)
    # The stylist who served the customer earns the commission; the cashier only when nobody else was named.
    seller = func.coalesce(Sale.sales_associate_id, Sale.cashier_id)
    sold = (
        select(seller, Product.category_id, SaleItem.line_total_cents, SaleItem.tax_cents, SaleItem.cost_cents)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
    )
    returned = (
        select(
            seller,
            Product.category_id,
            ReturnItem.refund_cents,
            ReturnItem.tax_refund_cents,
            ReturnItem.quantity,
            SaleItem.cost_cents,
            SaleItem.quantity,
        )
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == ReturnItem.product_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
    )
    if store_id is not None:
        sold = sold.where(Sale.store_id == store_id)
        returned = returned.where(SaleReturn.store_id == store_id)

    def credit(cashier: uuid.UUID, category: uuid.UUID | None, net: int, cost: int) -> None:
        who = person(cashier)
        if who is None:
            return
        rule = _pick(rules, str(category) if category else None, str(who.role_id))
        if rule is None:
            return
        basis[(cashier, rule.id)] += net if rule.basis == "NET_SALES" else net - cost

    for cashier, category, line_total, tax, cost in db.execute(sold):
        credit(cashier, category, line_total - tax, cost or 0)
        lines[cashier] += 1
    # Returns take back commission from whoever made the original sale.
    for cashier, category, refund, tax_refund, quantity, cost, sold_qty in db.execute(returned):
        credit(cashier, category, -(refund - tax_refund), -((cost or 0) * quantity // max(sold_qty, 1)))

    by_rule = {rule.id: rule for rule in rules}
    grouped: dict[uuid.UUID, list[CommissionByRule]] = defaultdict(list)
    for (cashier, rule_id), amount in basis.items():
        rule = by_rule[rule_id]
        earned = max(0, amount - rule.threshold_cents) * rule.rate_bps
        grouped[cashier].append(
            CommissionByRule(
                rule_id=rule_id, rule_name=rule.name, basis_cents=amount, commission_cents=(earned + 5000) // 10_000
            )
        )
    staff = [
        StaffCommission(
            user_id=cashier,
            name=users[cashier].full_name,
            role_name=users[cashier].role.name if users[cashier].role else "",
            lines=lines[cashier],
            commission_cents=sum(row.commission_cents for row in rows),
            by_rule=sorted(rows, key=lambda row: row.rule_name),
        )
        for cashier, rows in grouped.items()
    ]
    staff.sort(key=lambda row: -row.commission_cents)
    return CommissionReport(
        period_from=start,
        period_to=end,
        currency=business_currency(db),
        total_cents=sum(row.commission_cents for row in staff),
        staff=staff,
    )


# --- Payroll ----------------------------------------------------------------------------------------------


def payroll_settings(db: Session) -> PayrollSettings | None:
    raw = load_settings(db).payroll
    return PayrollSettings(**raw) if raw else None


def save_payroll_settings(db: Session, data: PayrollSettings) -> PayrollSettings:
    load_settings(db).payroll = data.model_dump()
    db.commit()
    return data


def employees(db: Session) -> list[EmployeeOut]:
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    out = []
    for user in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.full_name)).unique():
        profile = profiles.get(user.id)
        out.append(
            EmployeeOut(
                user_id=user.id,
                name=user.full_name,
                role_name=user.role.name if user.role else "",
                store_id=user.store_id,
                profile=EmployeeProfileWrite(
                    employee_code=profile.employee_code,
                    labour_id=profile.labour_id,
                    bank_routing_code=profile.bank_routing_code,
                    iban=profile.iban,
                    basic_salary_cents=profile.basic_salary_cents,
                    housing_allowance_cents=profile.housing_allowance_cents,
                    transport_allowance_cents=profile.transport_allowance_cents,
                    other_allowance_cents=profile.other_allowance_cents,
                    overtime_rate_pct=profile.overtime_rate_pct,
                    is_active=profile.is_active,
                )
                if profile
                else None,
            )
        )
    return out


def save_profile(db: Session, user_id: uuid.UUID, data: EmployeeProfileWrite) -> list[EmployeeOut]:
    if db.get(User, user_id) is None:
        raise ApiError(404, "not_found", "That person was not found.")
    profile = db.scalar(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
    if profile is None:
        profile = EmployeeProfile(user_id=user_id)
        db.add(profile)
    for key, value in data.model_dump().items():
        setattr(profile, key, value)
    db.commit()
    return employees(db)


def _leave_deduction(line: PayrollLine) -> int:
    return (line.basic_cents + line.allowances_cents) * line.unpaid_leave_days // 30


def _net(line: PayrollLine) -> int:
    return (
        line.basic_cents
        + line.allowances_cents
        + line.overtime_cents
        + line.commission_cents
        + line.bonus_cents
        - line.deductions_cents
        - _leave_deduction(line)
    )


def _run_out(db: Session, run: PayrollRun) -> PayrollRunOut:
    names = (
        {
            user.id: user.full_name
            for user in db.scalars(select(User).where(User.id.in_([line.user_id for line in run.lines]))).unique()
        }
        if run.lines
        else {}
    )
    return PayrollRunOut(
        id=run.id,
        year=run.year,
        month=run.month,
        status=run.status,  # type: ignore[arg-type]
        currency=run.currency,
        finalized_at=run.finalized_at
        if run.finalized_at is None or run.finalized_at.tzinfo
        else run.finalized_at.replace(tzinfo=UTC),
        total_net_cents=sum(line.net_cents for line in run.lines),
        lines=[
            PayrollLineOut(
                id=line.id,
                user_id=line.user_id,
                name=names.get(line.user_id, ""),
                employee_code=line.employee_code,
                basic_cents=line.basic_cents,
                allowances_cents=line.allowances_cents,
                overtime_minutes=line.overtime_minutes,
                overtime_cents=line.overtime_cents,
                commission_cents=line.commission_cents,
                bonus_cents=line.bonus_cents,
                deductions_cents=line.deductions_cents,
                unpaid_leave_days=line.unpaid_leave_days,
                leave_deduction_cents=_leave_deduction(line),
                note=line.note,
                net_cents=line.net_cents,
            )
            for line in run.lines
        ],
    )


def _period(run: PayrollRun) -> tuple[date, date]:
    return date(run.year, run.month, 1), date(run.year, run.month, calendar.monthrange(run.year, run.month)[1])


def _fill(db: Session, run: PayrollRun) -> None:
    """(Re)computes every active employee's line from their profile, approved overtime and commission."""
    start, end = _period(run)
    report = commissions(db, start=start, end=end, store_id=None)
    earned = {row.user_id: row.commission_cents for row in report.staff}
    existing = {line.user_id: line for line in run.lines}
    for profile in list(db.scalars(select(EmployeeProfile).where(EmployeeProfile.is_active.is_(True)))):
        _, overtime_minutes = timesheet_service.approved_minutes(db, user_id=profile.user_id, start=start, end=end)
        line = existing.get(profile.user_id)
        if line is None:
            line = PayrollLine(user_id=profile.user_id, employee_code=profile.employee_code, net_cents=0)
            run.lines.append(line)
        line.employee_code = profile.employee_code
        line.basic_cents = profile.basic_salary_cents
        line.allowances_cents = (
            profile.housing_allowance_cents + profile.transport_allowance_cents + profile.other_allowance_cents
        )
        line.overtime_minutes = overtime_minutes
        # Hourly basic rate is a month's basic over 30 days of 8 hours.
        line.overtime_cents = (
            profile.basic_salary_cents * overtime_minutes * profile.overtime_rate_pct // (30 * 8 * 60 * 100)
        )
        line.commission_cents = earned.get(profile.user_id, 0)
        line.bonus_cents = line.bonus_cents or 0
        line.deductions_cents = line.deductions_cents or 0
        line.unpaid_leave_days = line.unpaid_leave_days or 0
        line.net_cents = _net(line)


def _run(db: Session, run_id: uuid.UUID) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Payroll run was not found.")
    return run


def list_runs(db: Session) -> list[PayrollRunOut]:
    return [
        _run_out(db, run)
        for run in db.scalars(select(PayrollRun).order_by(PayrollRun.year.desc(), PayrollRun.month.desc()))
    ]


def create_run(db: Session, year: int, month: int, user_id: uuid.UUID | None) -> PayrollRunOut:
    if db.scalar(select(PayrollRun.id).where(PayrollRun.year == year, PayrollRun.month == month)):
        raise ApiError(409, "run_exists", f"Payroll for {calendar.month_name[month]} {year} already exists.")
    run = PayrollRun(year=year, month=month, currency=business_currency(db), created_by_id=user_id)
    db.add(run)
    db.flush()
    _fill(db, run)
    if not run.lines:
        db.rollback()
        raise ApiError(422, "no_employees", "Add payroll details for at least one employee first.")
    db.commit()
    return _run_out(db, run)


def recalculate(db: Session, run_id: uuid.UUID) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status != "DRAFT":
        raise ApiError(409, "run_final", "A finalized payroll cannot change.")
    _fill(db, run)
    db.commit()
    return _run_out(db, run)


def update_line(db: Session, run_id: uuid.UUID, line_id: uuid.UUID, data: PayrollLineWrite) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status != "DRAFT":
        raise ApiError(409, "run_final", "A finalized payroll cannot change.")
    line = next((row for row in run.lines if row.id == line_id), None)
    if line is None:
        raise ApiError(404, "not_found", "Payroll line was not found.")
    line.bonus_cents = data.bonus_cents
    line.deductions_cents = data.deductions_cents
    line.unpaid_leave_days = data.unpaid_leave_days
    line.note = data.note.strip()
    line.net_cents = _net(line)
    if line.net_cents < 0:
        db.rollback()
        raise ApiError(422, "negative_pay", "Deductions cannot exceed the month's pay.")
    db.commit()
    return _run_out(db, run)


def finalize(db: Session, run_id: uuid.UUID, user_id: uuid.UUID | None) -> PayrollRunOut:
    run = _run(db, run_id)
    if run.status != "DRAFT":
        raise ApiError(409, "run_final", "This payroll is already finalized.")
    run.status = "FINALIZED"
    run.finalized_by_id = user_id
    run.finalized_at = datetime.now(UTC)
    db.commit()
    return _run_out(db, run)


def wps_file(db: Session, run_id: uuid.UUID, now: datetime | None = None) -> tuple[str, str]:
    """The WPS Salary Information File: one EDR line per employee and an SCR control line. Returns (name, body)."""
    run = _run(db, run_id)
    if run.status != "FINALIZED":
        raise ApiError(409, "run_draft", "Finalize the payroll before exporting the WPS file.")
    employer = payroll_settings(db)
    if employer is None:
        raise ApiError(422, "wps_settings", "Enter the employer's MOHRE establishment ID and bank routing code first.")
    profiles = {row.user_id: row for row in db.scalars(select(EmployeeProfile))}
    start, end = _period(run)
    days = (end - start).days + 1
    rows = []
    total = 0
    for line in run.lines:
        profile = profiles.get(line.user_id)
        if profile is None or line.net_cents <= 0:
            continue
        variable = line.overtime_cents + line.commission_cents + line.bonus_cents
        fixed = line.net_cents - variable
        total += line.net_cents
        rows.append(
            ",".join(
                [
                    "EDR",
                    profile.labour_id,
                    profile.bank_routing_code,
                    profile.iban,
                    start.isoformat(),
                    end.isoformat(),
                    str(days),
                    f"{fixed / 100:.2f}",
                    f"{variable / 100:.2f}",
                    str(line.unpaid_leave_days),
                ]
            )
        )
    moment = now or datetime.now(UTC)
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
                f"{total / 100:.2f}",
                run.currency,
                f"SAL{run.year}{run.month:02d}",
            ]
        )
    )
    return f"{employer.employer_id}{moment:%y%m%d%H%M%S}.SIF", "\r\n".join(rows) + "\r\n"


def finalized_in(db: Session, since: datetime, until: datetime) -> list[PayrollRun]:
    return list(
        db.scalars(
            select(PayrollRun).where(
                PayrollRun.status == "FINALIZED", PayrollRun.finalized_at >= since, PayrollRun.finalized_at < until
            )
        )
    )
