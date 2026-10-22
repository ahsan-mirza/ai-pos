"""Customer credit risk: an explainable 0-100 score (higher is riskier), a grade A-E, the reasons behind it and a
suggested credit limit. Every point comes from a named factor so a manager can see why an account scored as it did;
there is no opaque model to trust.

Signals, from the account's own history:
- how overdue the open invoices are now, and what share of the balance is overdue,
- credit utilisation (balance against limit),
- how late past invoices were paid (replaying the ledger the way `ledger_service.receive_payment` allocates),
- bounced cheques and overdue reminders in the last year / quarter,
- an active credit hold, and how new the account is.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.cheque import Cheque
from app.models.customer import TERM_DAYS, Customer, CustomerLedgerEntry
from app.models.messaging import OutboundMessage
from app.models.sale import Sale
from app.schemas.wholesale import CreditRiskOut, RiskFactorOut
from app.services import ledger_service

GRADES = (
    ("A", 15, "Low risk"),
    ("B", 30, "Moderate"),
    ("C", 50, "Watch"),
    ("D", 70, "High risk"),
    ("E", 101, "Severe"),
)
RECOMMENDATIONS = {
    "A": "Reliable payer. Terms or the limit can be extended.",
    "B": "Normal terms.",
    "C": "Keep new credit within the limit and follow up on overdue invoices.",
    "D": "Ask for manager approval before more on-account sales.",
    "E": "Sell for cash or against payment until the account is brought up to date.",
}
# Months of typical purchases a limit should cover, by grade.
LIMIT_MONTHS = {"A": 1.5, "B": 1.2, "C": 1.0, "D": 0.6, "E": 0.0}


@dataclass(frozen=True)
class Features:
    balance_cents: int
    limit_cents: int
    overdue_cents: int
    max_days_overdue: int
    #: Amount-weighted average days late on invoices settled in the last year; None without settled invoices.
    avg_days_late: float | None
    settled_invoices: int
    bounced_cheques: int
    reminders_90d: int
    credit_hold: bool
    account_age_days: int
    monthly_purchases_cents: int
    payment_terms: str = "DUE_ON_RECEIPT"


@dataclass(frozen=True)
class Factor:
    key: str
    label: str
    points: int
    detail: str


@dataclass(frozen=True)
class CreditRisk:
    score: int
    grade: str
    label: str
    recommendation: str
    suggested_limit_cents: int
    factors: tuple[Factor, ...] = field(default_factory=tuple)

    def as_json(self) -> dict:
        return {
            "label": self.label,
            "recommendation": self.recommendation,
            "suggested_limit_cents": self.suggested_limit_cents,
            "factors": [factor.__dict__ for factor in self.factors],
        }


def _band(value: float, bands: tuple[tuple[float, int], ...]) -> int:
    for upper, points in bands:
        if value <= upper:
            return points
    return bands[-1][1]


def score(features: Features) -> CreditRisk:
    factors: list[Factor] = []

    def add(key: str, label: str, points: int, detail: str) -> None:
        if points:
            factors.append(Factor(key, label, points, detail))

    days = features.max_days_overdue
    add(
        "overdue_days",
        "Invoices overdue",
        _band(days, ((0, 0), (30, 15), (60, 25), (90, 35), (float("inf"), 45))),
        f"Oldest open invoice is {days} days past due.",
    )
    if features.balance_cents > 0 and features.overdue_cents > 0:
        share = features.overdue_cents / features.balance_cents
        add("overdue_share", "Share of balance overdue", round(share * 10), f"{share:.0%} of the balance is overdue.")
    if features.limit_cents > 0:
        use = features.balance_cents / features.limit_cents
        add(
            "utilisation",
            "Credit used",
            _band(use, ((0.5, 0), (0.8, 5), (1.0, 12), (float("inf"), 20))),
            f"Balance is {use:.0%} of the credit limit.",
        )
    elif features.balance_cents > 0:
        add("no_limit", "Balance without a limit", 10, "The account owes money but has no credit limit set.")
    if features.avg_days_late is None:
        add("thin_file", "No payment history", 5, "No invoices have been paid on this account yet.")
    else:
        late = features.avg_days_late
        add(
            "late_payment",
            "Pays late",
            _band(late, ((0.5, 0), (7, 5), (30, 12), (float("inf"), 20))),
            f"Invoices were paid {late:.0f} days after the due date on average "
            f"({features.settled_invoices} paid in the last year).",
        )
    if features.bounced_cheques:
        add(
            "bounced_cheques",
            "Bounced cheques",
            min(20, 10 * features.bounced_cheques),
            f"{features.bounced_cheques} cheque(s) bounced in the last year.",
        )
    if features.reminders_90d:
        add(
            "reminders",
            "Overdue reminders",
            min(9, 3 * features.reminders_90d),
            f"{features.reminders_90d} overdue reminder(s) sent in the last 90 days.",
        )
    if features.credit_hold:
        add("credit_hold", "On credit hold", 10, "The account is on credit hold.")
    if features.account_age_days < 90:
        add("new_account", "New account", 5, f"The account was opened {features.account_age_days} days ago.")

    total = min(100, sum(factor.points for factor in factors))
    grade, label = next((grade, label) for grade, upper, label in GRADES if total < upper)
    term_months = max(TERM_DAYS.get(features.payment_terms, 30), 30) / 30
    suggested = int(features.monthly_purchases_cents * term_months * LIMIT_MONTHS[grade]) // 100_00 * 100_00
    return CreditRisk(
        score=total,
        grade=grade,
        label=label,
        recommendation=RECOMMENDATIONS[grade],
        suggested_limit_cents=max(0, suggested),
        factors=tuple(sorted(factors, key=lambda factor: -factor.points)),
    )


def _payment_lateness(db: Session, customer: Customer, since: datetime) -> tuple[float | None, int]:
    """Replays the ledger oldest-invoice-first and measures how late each settled invoice was paid."""
    entries = db.execute(
        select(
            CustomerLedgerEntry.entry_type,
            CustomerLedgerEntry.amount_cents,
            CustomerLedgerEntry.created_at,
            CustomerLedgerEntry.sale_id,
        )
        .where(CustomerLedgerEntry.customer_id == customer.id)
        .order_by(CustomerLedgerEntry.created_at, CustomerLedgerEntry.id)
    ).all()
    sale_ids = {sale_id for kind, _, _, sale_id in entries if kind == "INVOICE" and sale_id is not None}
    dates = dict(db.execute(select(Sale.id, Sale.due_date).where(Sale.id.in_(sale_ids))).all()) if sale_ids else {}
    open_items: list[list] = []  # [remaining_cents, due_date, amount_cents]
    late_weighted = 0.0
    weight = 0
    settled = 0
    # Positive rows (invoices, debit adjustments) open items; negative rows (payments, credits) settle them.
    for _kind, amount, at, sale_id in entries:
        at = ledger_service.as_utc(at)
        if amount > 0:
            due = dates.get(sale_id) if sale_id is not None else None
            open_items.append([amount, ledger_service.as_utc(due) if due is not None else at, amount])
            continue
        remaining = -amount
        while remaining > 0 and open_items:
            item = open_items[0]
            applied = min(remaining, item[0])
            item[0] -= applied
            remaining -= applied
            if item[0] == 0:
                open_items.pop(0)
                if at >= since:
                    late_weighted += max(0.0, (at - item[1]).total_seconds() / 86_400) * item[2]
                    weight += item[2]
                    settled += 1
    return (late_weighted / weight if weight else None), settled


def features_for(db: Session, customer: Customer, now: datetime | None = None) -> Features:
    now = now or datetime.now(UTC)
    invoices = ledger_service.open_invoices(db, customer.id)
    overdue = [sale for sale in invoices if ledger_service.days_overdue(sale, now) > 0]
    avg_late, settled = _payment_lateness(db, customer, now - timedelta(days=365))
    bounced = db.scalar(
        select(func.count())
        .select_from(Cheque)
        .where(
            Cheque.customer_id == customer.id,
            Cheque.status == "BOUNCED",
            Cheque.updated_at >= now - timedelta(days=365),
        )
    )
    reminders = db.scalar(
        select(func.count())
        .select_from(OutboundMessage)
        .where(
            OutboundMessage.customer_id == customer.id,
            OutboundMessage.template_key == "overdue_reminder",
            OutboundMessage.created_at >= now - timedelta(days=90),
        )
    )
    purchased = db.scalar(
        select(func.coalesce(func.sum(Sale.total_cents), 0)).where(
            Sale.customer_id == customer.id,
            Sale.is_quote_proforma.is_(False),
            Sale.created_at >= now - timedelta(days=90),
        )
    )
    return Features(
        balance_cents=customer.current_balance_cents,
        limit_cents=customer.credit_limit_cents,
        overdue_cents=sum(sale.due_balance_cents for sale in overdue),
        max_days_overdue=max((ledger_service.days_overdue(sale, now) for sale in invoices), default=0),
        avg_days_late=avg_late,
        settled_invoices=settled,
        bounced_cheques=int(bounced or 0),
        reminders_90d=int(reminders or 0),
        credit_hold=customer.credit_hold,
        account_age_days=max(0, (now - ledger_service.as_utc(customer.created_at)).days),
        monthly_purchases_cents=int(purchased or 0) // 3,
        payment_terms=customer.payment_terms,
    )


def refresh(db: Session, customer: Customer, now: datetime | None = None) -> CreditRisk:
    now = now or datetime.now(UTC)
    risk = score(features_for(db, customer, now))
    customer.risk_score = risk.score
    customer.risk_grade = risk.grade
    customer.risk_detail = risk.as_json()
    customer.risk_computed_at = now
    return risk


def refresh_all(db: Session) -> int:
    customers = db.scalars(
        select(Customer).where(Customer.customer_type == "WHOLESALE", Customer.is_active.is_(True))
    ).all()
    for customer in customers:
        refresh(db, customer)
    db.commit()
    return len(customers)


def risk_out(customer: Customer) -> CreditRiskOut:
    detail = customer.risk_detail or {}
    return CreditRiskOut(
        customer_id=customer.id,
        code=customer.code,
        name=customer.company_name or customer.name,
        score=customer.risk_score or 0,
        grade=customer.risk_grade or "A",
        label=detail.get("label", ""),
        recommendation=detail.get("recommendation", ""),
        suggested_limit_cents=int(detail.get("suggested_limit_cents", 0)),
        credit_limit_cents=customer.credit_limit_cents,
        balance_cents=customer.current_balance_cents,
        factors=[RiskFactorOut(**factor) for factor in detail.get("factors", [])],
        computed_at=customer.risk_computed_at,
    )


def for_customer(db: Session, customer_id) -> CreditRiskOut:
    """Scores the account now, so the portal always shows today's picture."""
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise ApiError(404, "not_found", "Customer was not found.")
    refresh(db, customer)
    db.commit()
    return risk_out(customer)


def portfolio(db: Session, *, refresh_stale_hours: int = 24) -> list[CreditRiskOut]:
    """Every active wholesale account, riskiest first. Scores older than a day are recomputed."""
    now = datetime.now(UTC)
    customers = db.scalars(
        select(Customer).where(Customer.customer_type == "WHOLESALE", Customer.is_active.is_(True))
    ).all()
    stale = [
        customer
        for customer in customers
        if customer.risk_computed_at is None
        or ledger_service.as_utc(customer.risk_computed_at) < now - timedelta(hours=refresh_stale_hours)
    ]
    for customer in stale:
        refresh(db, customer, now)
    if stale:
        db.commit()
    return sorted((risk_out(customer) for customer in customers), key=lambda row: -row.score)
