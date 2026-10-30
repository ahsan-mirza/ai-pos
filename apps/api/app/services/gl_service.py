"""The general ledger. Every module posts here automatically: the posting engine turns the same document-level
journal the accounting export uses into journal entries, one per document, and keeps them in step with their
documents (a voided or edited document is reversed and reposted). Managers add manual journals, read the
statements, lock periods, close years and estimate UAE corporate tax."""

from __future__ import annotations

import hashlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.accounting import GlAccount, JournalEntry, JournalLine
from app.models.customer import Customer
from app.models.user import User
from app.schemas.accounting import (
    AccountingSettings,
    AccountLedger,
    BalanceSheet,
    CorporateTaxEstimate,
    GlAccountRow,
    GlAccountWrite,
    IncomeStatement,
    JournalEntryOut,
    JournalLineIn,
    JournalLineOut,
    LedgerRow,
    ManualJournalCreate,
    PostResult,
    StatementRow,
    StatementSection,
    SubledgerCheck,
    TrialBalance,
    TrialBalanceRow,
)
from app.services import export_service, management_reports, payables_service, race
from app.services.settings_service import business_currency, load_settings

log = logging.getLogger(__name__)

AUTO_WINDOW_DAYS = 45
DEBIT_NORMAL = ("ASSET", "EXPENSE")
# UAE corporate tax: 0% up to AED 375,000 of taxable income, 9% above it. Small business relief: revenue up to
# AED 3m, for tax periods starting on or before 31 December 2026.
CT_THRESHOLD_CENTS = 37_500_000
CT_RATE_BPS = 900
SBR_REVENUE_CENTS = 300_000_000
SBR_LAST_PERIOD_START = date(2026, 12, 31)


def _user_id(principal: Principal | None) -> uuid.UUID | None:
    return principal.user.id if principal is not None and principal.user else None


def _today() -> date:
    return datetime.now(UTC).date()


# --- Settings --------------------------------------------------------------------------------------


def settings(db: Session) -> AccountingSettings:
    row = load_settings(db)
    raw = row.accounting or {}
    locked = raw.get("locked_until")
    return AccountingSettings(
        fiscal_year_start_month=int(raw.get("fiscal_year_start_month") or 1),
        locked_until=date.fromisoformat(locked) if locked else None,
        inventory_costing=row.inventory_costing,
    )


def _save_settings(db: Session, value: AccountingSettings) -> None:
    load_settings(db).accounting = {
        "fiscal_year_start_month": value.fiscal_year_start_month,
        "locked_until": value.locked_until.isoformat() if value.locked_until else None,
    }


def update_settings(db: Session, fiscal_year_start_month: int) -> AccountingSettings:
    current = settings(db)
    current.fiscal_year_start_month = fiscal_year_start_month
    _save_settings(db, current)
    db.commit()
    return current


def lock(db: Session, locked_until: date | None) -> AccountingSettings:
    if locked_until is not None and locked_until >= _today():
        raise ApiError(422, "lock_in_future", "Lock the books up to yesterday at most.")
    current = settings(db)
    current.locked_until = locked_until
    _save_settings(db, current)
    db.commit()
    return current


def _open_date(day: date, locked: date | None) -> tuple[date, date | None]:
    """Where an entry for `day` goes: its own day, or the first open day when the books are locked for it."""
    if locked is not None and day <= locked:
        return locked + timedelta(days=1), day
    return day, None


def fiscal_year(db: Session, year: int) -> tuple[date, date]:
    month = settings(db).fiscal_year_start_month
    return date(year, month, 1), date(year + 1, month, 1) - timedelta(days=1)


# --- Accounts --------------------------------------------------------------------------------------


def _type_for(code: str) -> str:
    return {"1": "ASSET", "2": "LIABILITY", "3": "EQUITY", "4": "INCOME"}.get(code[:1], "EXPENSE")


def ensure_accounts(db: Session) -> dict[str, GlAccount]:
    """Every account the posting engine maps to exists; returns accounts by code."""
    accounts = {row.code: row for row in db.scalars(select(GlAccount))}
    missing = {
        code: GlAccount(code=code, name=name, type=_type_for(code), is_system=True, is_active=True)
        for code, name in export_service.chart_of_accounts(db).values()
        if code not in accounts
    }
    if not race.add_if_absent(db, missing.values()):
        return {row.code: row for row in db.scalars(select(GlAccount))}
    accounts.update(missing)
    return accounts


def _system_code(db: Session, key: str) -> str:
    return export_service.chart_of_accounts(db)[key][0]


def _balances(
    db: Session, *, start: date | None = None, end: date | None = None, exclude_closing: bool = False
) -> dict[uuid.UUID, tuple[int, int]]:
    query = (
        select(JournalLine.account_id, func.sum(JournalLine.debit_cents), func.sum(JournalLine.credit_cents))
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .group_by(JournalLine.account_id)
    )
    if start is not None:
        query = query.where(JournalEntry.entry_date >= start)
    if end is not None:
        query = query.where(JournalEntry.entry_date <= end)
    if exclude_closing:
        query = query.where(JournalEntry.journal != "CLOSING")
    return {row[0]: (int(row[1] or 0), int(row[2] or 0)) for row in db.execute(query)}


def _signed(account: GlAccount, debit: int, credit: int) -> int:
    """Balance in the account's normal direction: debits for assets and expenses, credits otherwise."""
    return debit - credit if account.type in DEBIT_NORMAL else credit - debit


def _account_row(account: GlAccount, totals: tuple[int, int]) -> GlAccountRow:
    return GlAccountRow(
        id=account.id,
        code=account.code,
        name=account.name,
        type=account.type,  # type: ignore[arg-type]
        is_system=account.is_system,
        is_active=account.is_active,
        balance_cents=_signed(account, *totals),
    )


def list_accounts(db: Session) -> list[GlAccountRow]:
    ensure_accounts(db)
    db.commit()
    totals = _balances(db)
    rows = db.scalars(select(GlAccount).order_by(GlAccount.code))
    return [_account_row(row, totals.get(row.id, (0, 0))) for row in rows]


def save_account(db: Session, data: GlAccountWrite, account_id: uuid.UUID | None = None) -> GlAccountRow:
    code = data.code.strip()
    clash = db.scalar(select(GlAccount.id).where(GlAccount.code == code))
    if account_id is None:
        if clash is not None:
            raise ApiError(409, "duplicate_code", f"Account {code} already exists.")
        account = GlAccount(code=code, name=data.name.strip(), type=data.type, is_system=False, is_active=True)
        db.add(account)
    else:
        account = db.get(GlAccount, account_id)
        if account is None:
            raise ApiError(404, "not_found", "Account was not found.")
        if clash is not None and clash != account.id:
            raise ApiError(409, "duplicate_code", f"Account {code} already exists.")
        used = db.scalar(select(JournalLine.id).where(JournalLine.account_id == account.id).limit(1))
        if account.is_system and (code != account.code or data.type != account.type or not data.is_active):
            raise ApiError(
                409, "system_account", "System accounts keep their code and type; rename them, or remap in Exports."
            )
        if used is not None and data.type != account.type:
            raise ApiError(409, "account_in_use", "This account has postings; its type can no longer change.")
        account.code = code
        account.name = data.name.strip()
        account.type = data.type
        account.is_active = data.is_active
    db.commit()
    return _account_row(account, _balances(db).get(account.id, (0, 0)))


# --- Posting ---------------------------------------------------------------------------------------


@dataclass
class _Draft:
    source: str
    journal: str
    reference: str
    day: date
    lines: list[tuple[str, int, int, str]] = field(default_factory=list)


def _drafts(lines: list[export_service.JournalLine]) -> dict[str, _Draft]:
    drafts: dict[str, _Draft] = {}
    for line in lines:
        if not line.source:
            continue
        draft = drafts.get(line.source)
        if draft is None:
            draft = drafts[line.source] = _Draft(line.source, line.journal, line.reference, line.day)
        debit, credit = line.debit - line.credit, 0
        if debit < 0:
            debit, credit = 0, -debit
        if debit or credit:
            draft.lines.append((line.account, debit, credit, line.memo))
    return drafts


def _fingerprint(lines: list[tuple[str, int, int, str]]) -> str:
    totals: dict[str, int] = defaultdict(int)
    for code, debit, credit, _ in lines:
        totals[code] += debit - credit
    text = "|".join(f"{code}:{value}" for code, value in sorted(totals.items()) if value)
    return hashlib.sha256(text.encode()).hexdigest()


class _Numbers:
    def __init__(self, db: Session) -> None:
        self.next = int(db.scalar(select(func.max(JournalEntry.number))) or 0) + 1

    def take(self) -> int:
        value = self.next
        self.next += 1
        return value


def _write(
    db: Session,
    numbers: _Numbers,
    *,
    journal: str,
    reference: str,
    memo: str,
    day: date,
    lines: list[tuple[uuid.UUID, int, int, str]],
    locked: date | None,
    user_id: uuid.UUID | None,
    source_ref: str | None = None,
    fingerprint: str | None = None,
    reversal_of_id: uuid.UUID | None = None,
    force_date: bool = False,
) -> JournalEntry:
    entry_date, original = (day, None) if force_date else _open_date(day, locked)
    entry = JournalEntry(
        number=numbers.take(),
        entry_date=entry_date,
        original_date=original,
        journal=journal,
        reference=reference[:80],
        memo=(memo or (f"Late posting for {original.isoformat()}" if original else ""))[:255],
        source_ref=source_ref,
        fingerprint=fingerprint,
        is_active=True,
        reversal_of_id=reversal_of_id,
        created_by_id=user_id,
    )
    for position, (account_id, debit, credit, line_memo) in enumerate(lines):
        entry.lines.append(
            JournalLine(
                account_id=account_id,
                position=position,
                debit_cents=debit,
                credit_cents=credit,
                memo=line_memo[:255],
            )
        )
    db.add(entry)
    return entry


def _reverse(
    db: Session,
    numbers: _Numbers,
    entry: JournalEntry,
    *,
    locked: date | None,
    user_id: uuid.UUID | None,
    memo: str,
    day: date | None = None,
) -> JournalEntry:
    entry.is_active = False
    return _write(
        db,
        numbers,
        journal="REVERSAL",
        reference=entry.reference,
        memo=memo or f"Reverses JV {entry.number}",
        day=day or entry.entry_date,
        lines=[(line.account_id, line.credit_cents, line.debit_cents, line.memo) for line in entry.lines],
        locked=locked,
        user_id=user_id,
        reversal_of_id=entry.id,
    )


def post_period(db: Session, start: date, end: date, user_id: uuid.UUID | None = None) -> PostResult:
    """Bring the ledger in step with every document dated start..end. Safe to run any number of times."""
    accounts = ensure_accounts(db)
    locked = settings(db).locked_until
    drafts = _drafts(export_service.journal(db, start, end, None))
    dated = func.coalesce(JournalEntry.original_date, JournalEntry.entry_date)
    existing = {
        entry.source_ref: entry
        for entry in db.scalars(
            select(JournalEntry).where(
                JournalEntry.is_active.is_(True),
                JournalEntry.source_ref.is_not(None),
                and_(dated >= start, dated <= end),
            )
        )
    }
    numbers = _Numbers(db)
    posted = reversed_count = unchanged = 0
    unbalanced: list[str] = []
    for source, draft in drafts.items():
        if not draft.lines:
            continue
        if sum(line[1] for line in draft.lines) != sum(line[2] for line in draft.lines):
            unbalanced.append(source)
            log.warning("journal for %s does not balance; not posted", source)
            continue
        fingerprint = _fingerprint(draft.lines)
        current = existing.pop(source, None)
        if current is not None and current.fingerprint == fingerprint:
            unchanged += 1
            continue
        if current is not None:
            _reverse(db, numbers, current, locked=locked, user_id=user_id, memo=f"{draft.reference} changed")
            reversed_count += 1
        _write(
            db,
            numbers,
            journal=draft.journal,
            reference=draft.reference,
            memo="",
            day=draft.day,
            lines=[(accounts[code].id, debit, credit, memo) for code, debit, credit, memo in draft.lines],
            locked=locked,
            user_id=user_id,
            source_ref=source,
            fingerprint=fingerprint,
        )
        posted += 1
    for entry in existing.values():
        _reverse(db, numbers, entry, locked=locked, user_id=user_id, memo=f"{entry.reference} voided")
        reversed_count += 1
    db.commit()
    return PostResult(posted=posted, reversed=reversed_count, unchanged=unchanged, unbalanced=unbalanced)


def post_recent(db: Session) -> PostResult:
    today = _today()
    return post_period(db, today - timedelta(days=AUTO_WINDOW_DAYS), today)


def post_range(db: Session, principal: Principal, start: date, end: date) -> PostResult:
    if end < start:
        raise ApiError(422, "validation_error", "The period must end after it starts.")
    totals = PostResult(posted=0, reversed=0, unchanged=0, unbalanced=[])
    cursor = start
    while cursor <= end:
        stop = min(cursor + timedelta(days=89), end)
        part = post_period(db, cursor, stop, _user_id(principal))
        totals.posted += part.posted
        totals.reversed += part.reversed
        totals.unchanged += part.unchanged
        totals.unbalanced.extend(part.unbalanced)
        cursor = stop + timedelta(days=1)
    return totals


# --- Journals --------------------------------------------------------------------------------------


def _entry_out(
    entry: JournalEntry, accounts: dict[uuid.UUID, GlAccount], names: dict[uuid.UUID, str]
) -> JournalEntryOut:
    return JournalEntryOut(
        id=entry.id,
        number=entry.number,
        entry_date=entry.entry_date,
        original_date=entry.original_date,
        journal=entry.journal,
        reference=entry.reference,
        memo=entry.memo,
        source_ref=entry.source_ref,
        is_active=entry.is_active,
        reversal_of_id=entry.reversal_of_id,
        reversible=entry.journal == "MANUAL" and entry.is_active,
        total_cents=sum(line.debit_cents for line in entry.lines),
        created_by_name=names.get(entry.created_by_id) if entry.created_by_id else None,
        created_at=entry.created_at,
        lines=[
            JournalLineOut(
                account_id=line.account_id,
                account_code=accounts[line.account_id].code if line.account_id in accounts else "",
                account_name=accounts[line.account_id].name if line.account_id in accounts else "",
                debit_cents=line.debit_cents,
                credit_cents=line.credit_cents,
                memo=line.memo,
            )
            for line in entry.lines
        ],
    )


def _entries_out(db: Session, entries: list[JournalEntry]) -> list[JournalEntryOut]:
    accounts = {row.id: row for row in db.scalars(select(GlAccount))}
    users = {entry.created_by_id for entry in entries if entry.created_by_id}
    names = (
        {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(users))).unique()} if users else {}
    )
    return [_entry_out(entry, accounts, names) for entry in entries]


def list_journals(
    db: Session,
    *,
    start: date | None,
    end: date | None,
    journal: str | None,
    query: str | None,
    offset: int,
    limit: int,
) -> tuple[list[JournalEntryOut], int]:
    statement = select(JournalEntry)
    if start is not None:
        statement = statement.where(JournalEntry.entry_date >= start)
    if end is not None:
        statement = statement.where(JournalEntry.entry_date <= end)
    if journal:
        statement = statement.where(JournalEntry.journal == journal)
    if query:
        like = f"%{query.strip()}%"
        statement = statement.where(or_(JournalEntry.reference.ilike(like), JournalEntry.memo.ilike(like)))
    total = int(db.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    entries = list(
        db.scalars(
            statement.order_by(JournalEntry.entry_date.desc(), JournalEntry.number.desc()).offset(offset).limit(limit)
        )
    )
    return _entries_out(db, entries), total


def create_manual(db: Session, principal: Principal, data: ManualJournalCreate) -> JournalEntryOut:
    locked = settings(db).locked_until
    if locked is not None and data.entry_date <= locked:
        raise ApiError(409, "period_locked", f"The books are locked up to {locked:%d %b %Y}.")
    accounts = {
        row.id: row
        for row in db.scalars(select(GlAccount).where(GlAccount.id.in_([line.account_id for line in data.lines])))
    }
    for line in data.lines:
        account = accounts.get(line.account_id)
        if account is None or not account.is_active:
            raise ApiError(422, "unknown_account", "Every line needs an active account.")
        if (line.debit_cents > 0) == (line.credit_cents > 0):
            raise ApiError(422, "one_sided", f"Each line is either a debit or a credit ({account.code}).")
    debits = sum(line.debit_cents for line in data.lines)
    credits = sum(line.credit_cents for line in data.lines)
    if debits != credits:
        raise ApiError(422, "unbalanced", f"Debits {debits / 100:,.2f} and credits {credits / 100:,.2f} must match.")
    entry = _write(
        db,
        _Numbers(db),
        journal="MANUAL",
        reference=data.reference.strip(),
        memo=data.memo.strip(),
        day=data.entry_date,
        lines=[(line.account_id, line.debit_cents, line.credit_cents, line.memo.strip()) for line in data.lines],
        locked=locked,
        user_id=_user_id(principal),
    )
    db.commit()
    return _entries_out(db, [entry])[0]


def reverse_manual(
    db: Session, principal: Principal, entry_id: uuid.UUID, day: date | None, memo: str
) -> JournalEntryOut:
    entry = db.get(JournalEntry, entry_id)
    if entry is None:
        raise ApiError(404, "not_found", "Journal entry was not found.")
    if entry.journal != "MANUAL":
        raise ApiError(409, "not_manual", "Automatic entries follow their documents; correct the document instead.")
    if not entry.is_active:
        raise ApiError(409, "already_reversed", "This entry is already reversed.")
    locked = settings(db).locked_until
    if day is not None and locked is not None and day <= locked:
        raise ApiError(409, "period_locked", f"The books are locked up to {locked:%d %b %Y}.")
    reversal = _reverse(db, _Numbers(db), entry, locked=locked, user_id=_user_id(principal), memo=memo.strip(), day=day)
    db.commit()
    return _entries_out(db, [reversal])[0]


# --- Statements ------------------------------------------------------------------------------------


def trial_balance(db: Session, start: date, end: date) -> TrialBalance:
    ensure_accounts(db)
    db.commit()
    opening = _balances(db, end=start - timedelta(days=1))
    period = _balances(db, start=start, end=end)
    rows = []
    for account in db.scalars(select(GlAccount).order_by(GlAccount.code)):
        before = opening.get(account.id, (0, 0))
        moved = period.get(account.id, (0, 0))
        if before == (0, 0) and moved == (0, 0):
            continue
        open_value = before[0] - before[1]
        rows.append(
            TrialBalanceRow(
                account_id=account.id,
                code=account.code,
                name=account.name,
                type=account.type,  # type: ignore[arg-type]
                opening_cents=open_value,
                debit_cents=moved[0],
                credit_cents=moved[1],
                closing_cents=open_value + moved[0] - moved[1],
            )
        )
    return TrialBalance(
        period_from=start,
        period_to=end,
        currency=business_currency(db),
        rows=rows,
        total_debit_cents=sum(row.debit_cents for row in rows),
        total_credit_cents=sum(row.credit_cents for row in rows),
    )


def _section(key: str, title: str, rows: list[StatementRow]) -> StatementSection:
    kept = [row for row in rows if row.amount_cents]
    return StatementSection(key=key, title=title, rows=kept, total_cents=sum(row.amount_cents for row in kept))


def _checks(db: Session, totals: dict[uuid.UUID, tuple[int, int]], accounts: list[GlAccount]) -> list[SubledgerCheck]:
    by_code = {account.code: account for account in accounts}

    def books(key: str) -> int:
        account = by_code.get(_system_code(db, key))
        return _signed(account, *totals.get(account.id, (0, 0))) if account else 0

    stock = management_reports.valuation(db, store_id=None).cost_value_cents
    receivable = int(db.scalar(select(func.coalesce(func.sum(Customer.current_balance_cents), 0))) or 0)
    summary = payables_service.summary(db)
    payable = summary.outstanding_cents - sum(row.credit_cents for row in summary.suppliers)
    out = []
    for key, label, ledger in (
        ("inventory", "Stock on the books vs FIFO valuation", stock),
        ("receivables", "Receivables vs customer balances", receivable),
        ("payables", "Payables vs supplier balances", payable),
    ):
        value = books(key if key != "receivables" else "on_account")
        out.append(
            SubledgerCheck(
                key=key,  # type: ignore[arg-type]
                label=label,
                books_cents=value,
                subledger_cents=ledger,
                difference_cents=value - ledger,
            )
        )
    return out


def balance_sheet(db: Session, as_of: date) -> BalanceSheet:
    ensure_accounts(db)
    db.commit()
    totals = _balances(db, end=as_of)
    accounts = list(db.scalars(select(GlAccount).order_by(GlAccount.code)))
    grouped: dict[str, list[StatementRow]] = defaultdict(list)
    earnings = 0
    for account in accounts:
        debit, credit = totals.get(account.id, (0, 0))
        if account.type in ("INCOME", "EXPENSE"):
            earnings += credit - debit
            continue
        grouped[account.type].append(
            StatementRow(
                account_id=account.id,
                code=account.code,
                name=account.name,
                amount_cents=_signed(account, debit, credit),
            )
        )
    grouped["EQUITY"].append(
        StatementRow(account_id=None, code="", name="Current earnings (not yet closed)", amount_cents=earnings)
    )
    sections = [
        _section("assets", "Assets", grouped["ASSET"]),
        _section("liabilities", "Liabilities", grouped["LIABILITY"]),
        _section("equity", "Equity", grouped["EQUITY"]),
    ]
    assets, liabilities, equity = (section.total_cents for section in sections)
    return BalanceSheet(
        as_of=as_of,
        currency=business_currency(db),
        sections=sections,
        total_assets_cents=assets,
        total_liabilities_cents=liabilities,
        total_equity_cents=equity,
        balanced=assets == liabilities + equity,
        checks=_checks(db, totals, accounts) if as_of >= _today() else [],
    )


def income_statement(db: Session, start: date, end: date) -> IncomeStatement:
    ensure_accounts(db)
    db.commit()
    totals = _balances(db, start=start, end=end, exclude_closing=True)
    tax_code = _system_code(db, "corporate_tax_expense")
    revenue: list[StatementRow] = []
    cost: list[StatementRow] = []
    expenses: list[StatementRow] = []
    tax: list[StatementRow] = []
    for account in db.scalars(
        select(GlAccount).where(GlAccount.type.in_(("INCOME", "EXPENSE"))).order_by(GlAccount.code)
    ):
        debit, credit = totals.get(account.id, (0, 0))
        row = StatementRow(
            account_id=account.id, code=account.code, name=account.name, amount_cents=_signed(account, debit, credit)
        )
        if account.type == "INCOME":
            revenue.append(row)
        elif account.code == tax_code:
            tax.append(row)
        elif account.code.startswith("5"):
            cost.append(row)
        else:
            expenses.append(row)
    sections = [
        _section("revenue", "Revenue", revenue),
        _section("cost_of_sales", "Cost of sales", cost),
        _section("expenses", "Operating expenses", expenses),
        _section("tax", "Corporate tax", tax),
    ]
    gross = sections[0].total_cents - sections[1].total_cents
    operating = gross - sections[2].total_cents
    return IncomeStatement(
        period_from=start,
        period_to=end,
        currency=business_currency(db),
        sections=sections,
        gross_profit_cents=gross,
        operating_profit_cents=operating,
        net_profit_cents=operating - sections[3].total_cents,
    )


def account_ledger(db: Session, account_id: uuid.UUID, start: date, end: date, limit: int = 1000) -> AccountLedger:
    account = db.get(GlAccount, account_id)
    if account is None:
        raise ApiError(404, "not_found", "Account was not found.")
    before = _balances(db, end=start - timedelta(days=1)).get(account.id, (0, 0))
    opening = _signed(account, *before)
    rows_query = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.entry_id)
        .where(JournalLine.account_id == account.id, JournalEntry.entry_date >= start, JournalEntry.entry_date <= end)
        .order_by(JournalEntry.entry_date, JournalEntry.number, JournalLine.position)
    )
    data = db.execute(rows_query.limit(limit + 1)).all()
    balance = opening
    rows = []
    for line, entry in data[:limit]:
        balance += _signed(account, line.debit_cents, line.credit_cents)
        rows.append(
            LedgerRow(
                entry_id=entry.id,
                number=entry.number,
                entry_date=entry.entry_date,
                journal=entry.journal,
                reference=entry.reference,
                memo=line.memo or entry.memo,
                debit_cents=line.debit_cents,
                credit_cents=line.credit_cents,
                balance_cents=balance,
            )
        )
    period = _balances(db, start=start, end=end).get(account.id, (0, 0))
    return AccountLedger(
        account=_account_row(account, _balances(db).get(account.id, (0, 0))),
        period_from=start,
        period_to=end,
        opening_cents=opening,
        closing_cents=opening + _signed(account, *period),
        rows=rows,
        truncated=len(data) > limit,
    )


# --- Closing ---------------------------------------------------------------------------------------


def close_year(db: Session, principal: Principal, year_end: date) -> JournalEntryOut | None:
    """Move the year's income and expense balances to retained earnings, then lock the year."""
    current = settings(db)
    following = year_end + timedelta(days=1)
    start = date(following.year - 1, following.month, 1)
    if following.day != 1 or following.month != current.fiscal_year_start_month:
        raise ApiError(
            422,
            "not_year_end",
            "Pick the last day of a financial year; the year starts in month "
            f"{current.fiscal_year_start_month} (change it in accounting settings).",
        )
    if year_end >= _today():
        raise ApiError(422, "year_not_over", "A year can be closed once it has ended.")
    done = db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.journal == "CLOSING", JournalEntry.entry_date == year_end, JournalEntry.is_active.is_(True)
        )
    )
    if done is not None:
        raise ApiError(409, "already_closed", f"The year ending {year_end:%d %b %Y} is already closed.")
    accounts = ensure_accounts(db)
    post_period(db, start, year_end, _user_id(principal))
    totals = _balances(db, start=start, end=year_end, exclude_closing=True)
    retained = accounts[_system_code(db, "retained_earnings")]
    lines: list[tuple[uuid.UUID, int, int, str]] = []
    net = 0
    for account in db.scalars(select(GlAccount).where(GlAccount.type.in_(("INCOME", "EXPENSE")))):
        debit, credit = totals.get(account.id, (0, 0))
        balance = debit - credit
        if balance > 0:
            lines.append((account.id, 0, balance, "Close to retained earnings"))
        elif balance < 0:
            lines.append((account.id, -balance, 0, "Close to retained earnings"))
        net += credit - debit
    entry = None
    if lines:
        lines.append(
            (retained.id, 0, net, "Profit for the year") if net >= 0 else (retained.id, -net, 0, "Loss for the year")
        )
        entry = _write(
            db,
            _Numbers(db),
            journal="CLOSING",
            reference=f"FY {start.year}" if start.year == year_end.year else f"FY {start.year}/{year_end.year}",
            memo=f"Year-end close {start:%d %b %Y} – {year_end:%d %b %Y}",
            day=year_end,
            lines=lines,
            locked=None,
            user_id=_user_id(principal),
            force_date=True,
        )
    if current.locked_until is None or current.locked_until < year_end:
        current.locked_until = year_end
        _save_settings(db, current)
    db.commit()
    return _entries_out(db, [entry])[0] if entry is not None else None


# --- Corporate tax ---------------------------------------------------------------------------------


def corporate_tax(db: Session, year: int, add_backs_cents: int, deductions_cents: int) -> CorporateTaxEstimate:
    start, end = fiscal_year(db, year)
    statement = income_statement(db, start, end)
    revenue = statement.sections[0].total_cents
    before_tax = statement.operating_profit_cents
    taxable = before_tax + add_backs_cents - deductions_cents
    tax = max(taxable - CT_THRESHOLD_CENTS, 0) * CT_RATE_BPS // 10_000
    eligible = revenue <= SBR_REVENUE_CENTS and start <= SBR_LAST_PERIOD_START
    currency = business_currency(db)
    notes = [
        "Estimate from the ledger. Taxable income starts from accounting profit; add back non-deductible items "
        "(for example 50% of entertainment, fines, donations to non-qualifying bodies) and deduct exempt income.",
        "0% on the first AED 375,000 of taxable income, 9% above it.",
    ]
    if eligible:
        notes.append(
            "Revenue is within AED 3m, so the business can elect small business relief for this period and pay no "
            "corporate tax (the return is still filed)."
        )
    if taxable < 0:
        notes.append("A tax loss can be carried forward and set off against up to 75% of future taxable income.")
    if currency != "AED":
        notes.append(f"Amounts are in {currency}; the AED thresholds above are not converted.")
    provision_code = _system_code(db, "corporate_tax_expense")
    account = db.scalar(select(GlAccount).where(GlAccount.code == provision_code))
    posted = 0
    if account is not None:
        debit, credit = _balances(db, start=start, end=end, exclude_closing=True).get(account.id, (0, 0))
        posted = debit - credit
    return CorporateTaxEstimate(
        fiscal_year=year,
        period_from=start,
        period_to=end,
        currency=currency,
        revenue_cents=revenue,
        profit_before_tax_cents=before_tax,
        add_backs_cents=add_backs_cents,
        deductions_cents=deductions_cents,
        taxable_income_cents=taxable,
        threshold_cents=CT_THRESHOLD_CENTS,
        rate_bps=CT_RATE_BPS,
        tax_cents=tax,
        small_business_relief_eligible=eligible,
        provision_posted_cents=posted,
        notes=notes,
    )


def post_provision(db: Session, principal: Principal, year: int, amount_cents: int) -> JournalEntryOut:
    start, end = fiscal_year(db, year)
    accounts = ensure_accounts(db)
    expense = accounts[_system_code(db, "corporate_tax_expense")]
    payable = accounts[_system_code(db, "corporate_tax")]
    day = min(end, _today())
    return create_manual(
        db,
        principal,
        ManualJournalCreate(
            entry_date=day,
            reference=f"CT FY{year}",
            memo=f"Corporate tax provision, financial year {start:%d %b %Y} – {end:%d %b %Y}",
            lines=[
                JournalLineIn(account_id=expense.id, debit_cents=amount_cents, memo="Corporate tax"),
                JournalLineIn(account_id=payable.id, credit_cents=amount_cents, memo="Corporate tax payable"),
            ],
        ),
    )


def job(db: Session) -> str:
    result = post_recent(db)
    return f"{result.posted} posted, {result.reversed} reversed, {result.unchanged} unchanged"
