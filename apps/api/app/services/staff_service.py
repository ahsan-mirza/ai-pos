"""Sales commissions, employee payroll profiles, monthly payroll runs, and the UAE WPS salary file (SIF)."""

from __future__ import annotations

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
from app.models.staff import CommissionRule, PayrollRun
from app.models.user import User
from app.schemas.staff import (
    CommissionByRule,
    CommissionReport,
    CommissionRuleOut,
    CommissionRuleWrite,
    EmployeeOut,
    EmployeeProfileWrite,
    PayrollLineWrite,
    PayrollPaymentOut,
    PayrollPaymentWrite,
    PayrollRunOut,
    PayrollSettings,
    PayslipSummary,
    SalaryVersionOut,
    StaffCommission,
    WpsValidation,
)
from app.services.settings_service import business_currency

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


# --- Payroll -------------------------------------------------------------------------------------------------
# The calculation, versions, and WPS file live in payroll_engine. These names stay so existing callers keep working.


def _payroll():
    from app.services import payroll_engine

    return payroll_engine


def payroll_settings(db: Session) -> PayrollSettings | None:
    return _payroll().payroll_settings(db)


def save_payroll_settings(db: Session, data: PayrollSettings) -> PayrollSettings:
    return _payroll().save_payroll_settings(db, data)


def employees(db: Session, *, reveal_bank: bool = False, home_store_id: uuid.UUID | None = None) -> list[EmployeeOut]:
    return _payroll().employees(db, reveal_bank=reveal_bank, home_store_id=home_store_id)


def employee_detail(
    db: Session, user_id: uuid.UUID, *, reveal_bank: bool, home_store_id: uuid.UUID | None = None
) -> EmployeeOut:
    return _payroll().employee_detail(db, user_id, reveal_bank=reveal_bank, home_store_id=home_store_id)


def salary_history(db: Session, user_id: uuid.UUID) -> list[SalaryVersionOut]:
    return _payroll().salary_history(db, user_id)


def save_profile(
    db: Session,
    user_id: uuid.UUID,
    data: EmployeeProfileWrite,
    *,
    actor_id: uuid.UUID | None = None,
    home_store_id: uuid.UUID | None = None,
) -> list[EmployeeOut]:
    return _payroll().save_profile(db, user_id, data, actor_id=actor_id, home_store_id=home_store_id)


def list_runs(db: Session, *, home_store_id: uuid.UUID | None = None) -> list[PayrollRunOut]:
    return _payroll().list_runs(db, home_store_id=home_store_id)


def create_run(
    db: Session,
    year: int,
    month: int,
    user_id: uuid.UUID | None,
    store_id: uuid.UUID | None = None,
    home_store_id: uuid.UUID | None = None,
) -> PayrollRunOut:
    return _payroll().create_run(db, year, month, user_id, store_id=store_id, home_store_id=home_store_id)


def recalculate(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None = None) -> PayrollRunOut:
    return _payroll().recalculate(db, run_id, actor_id)


def update_line(db: Session, run_id: uuid.UUID, line_id: uuid.UUID, data: PayrollLineWrite) -> PayrollRunOut:
    return _payroll().update_line(db, run_id, line_id, data)


def submit_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None) -> PayrollRunOut:
    return _payroll().submit_run(db, run_id, actor_id)


def reject_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str) -> PayrollRunOut:
    return _payroll().reject_run(db, run_id, actor_id, note)


def return_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str) -> PayrollRunOut:
    return _payroll().return_run(db, run_id, actor_id, note)


def finalize(db: Session, run_id: uuid.UUID, user_id: uuid.UUID | None) -> PayrollRunOut:
    return _payroll().finalize(db, run_id, user_id)


def cancel_run(db: Session, run_id: uuid.UUID, actor_id: uuid.UUID | None, note: str = "") -> PayrollRunOut:
    return _payroll().cancel_run(db, run_id, actor_id, note)


def validate_wps(db: Session, run_id: uuid.UUID) -> WpsValidation:
    return _payroll().validate_wps(db, run_id)


def wps_file(
    db: Session, run_id: uuid.UUID, now: datetime | None = None, actor_id: uuid.UUID | None = None
) -> tuple[str, str]:
    return _payroll().wps_file(db, run_id, now=now, actor_id=actor_id)


def list_payments(db: Session, run_id: uuid.UUID) -> list[PayrollPaymentOut]:
    return _payroll().list_payments(db, run_id)


def record_payment(
    db: Session, run_id: uuid.UUID, data: PayrollPaymentWrite, actor_id: uuid.UUID | None
) -> list[PayrollPaymentOut]:
    return _payroll().record_payment(db, run_id, data, actor_id)


def payslips_for(db: Session, user_id: uuid.UUID) -> list[PayslipSummary]:
    return _payroll().payslips_for(db, user_id)


def finalized_in(db: Session, since: datetime, until: datetime) -> list[PayrollRun]:
    return _payroll().finalized_in(db, since, until)
