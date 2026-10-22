"""Bank reconciliation: statement lines on one side, what the books say went through the bank on the other.

Book items are derived from the records that already exist (sales tenders, account receipts, cheques, supplier
payments, expenses, petty cash top-ups, payroll); nothing is copied. Amounts are signed the same way as the
statement: money into the bank is positive.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.banking import BankAccount, BankStatement, BankStatementLine
from app.models.batch import Supplier
from app.models.cheque import Cheque
from app.models.customer import CustomerLedgerEntry
from app.models.expense import Expense, PettyCashEntry
from app.models.payables import SupplierPayment
from app.models.return_tender import ReturnTender
from app.models.sale import Sale
from app.models.sale_return import SaleReturn
from app.models.sale_tender import SaleTender
from app.models.store import Store
from app.models.user import User
from app.schemas.banking import (
    AutoMatchOut,
    BankAccountOut,
    BankAccountWrite,
    BookItemOut,
    CandidateOut,
    ReconciliationSummary,
    StatementImportOut,
    StatementLineOut,
    StatementOut,
)
from app.services import staff_service
from app.services.bank_statement_parser import line_hashes, parse
from app.services.numbering import next_server_number
from app.services.settings_service import business_currency

POSTED_SALES = ("completed", "partially_refunded", "refunded")
SETTLEMENT_KINDS = ("CARD_SETTLEMENT", "QR_SETTLEMENT", "BNPL_SETTLEMENT")
SETTLEMENT_OF_METHOD = {
    "card": ("CARD_SETTLEMENT", "Card"),
    "qr": ("QR_SETTLEMENT", "QR"),
    "bnpl": ("BNPL_SETTLEMENT", "Pay-later"),
}
AUTO_FEE_BPS = 350
MANUAL_FEE_BPS = 1_000
FEE_REFERENCE = "BANKREC"
# How far the bank date may sit from the book date: (days before, days after).
WINDOWS = {
    "CARD_SETTLEMENT": (0, 4),
    "QR_SETTLEMENT": (0, 4),
    # Tabby and Tamara pay out in weekly batches.
    "BNPL_SETTLEMENT": (0, 10),
    "TRANSFER_RECEIPT": (3, 5),
    "ACCOUNT_RECEIPT": (3, 5),
    "CHEQUE_DEPOSIT": (3, 14),
    "SUPPLIER_PAYMENT": (3, 30),
    "EXPENSE": (3, 7),
    "PETTY_CASH_TOPUP": (3, 3),
    "PAYROLL": (3, 10),
}
LOOKBACK_DAYS = 35


@dataclass
class BookItem:
    key: str
    kind: str
    booked_on: date
    amount_cents: int
    label: str
    reference: str = ""
    store_id: uuid.UUID | None = None


def _user_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user else None


def _day(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


# --- Accounts ------------------------------------------------------------------------------------


def _account(db: Session, account_id: uuid.UUID) -> BankAccount:
    account = db.get(BankAccount, account_id)
    if account is None:
        raise ApiError(404, "not_found", "Bank account was not found.")
    return account


def _last_line(db: Session, account_id: uuid.UUID) -> BankStatementLine | None:
    return db.scalars(
        select(BankStatementLine)
        .where(BankStatementLine.account_id == account_id)
        .order_by(BankStatementLine.booked_on.desc(), BankStatementLine.created_at.desc())
        .limit(1)
    ).first()


def _balance(db: Session, account_id: uuid.UUID) -> int | None:
    row = db.scalars(
        select(BankStatementLine.balance_cents)
        .where(BankStatementLine.account_id == account_id, BankStatementLine.balance_cents.is_not(None))
        .order_by(BankStatementLine.booked_on.desc(), BankStatementLine.created_at.desc())
        .limit(1)
    ).first()
    return row


def _account_out(db: Session, account: BankAccount) -> BankAccountOut:
    unmatched = db.scalar(
        select(func.count())
        .select_from(BankStatementLine)
        .where(BankStatementLine.account_id == account.id, BankStatementLine.status == "UNMATCHED")
    )
    last = _last_line(db, account.id)
    return BankAccountOut(
        id=account.id,
        name=account.name,
        bank=account.bank,
        iban=account.iban,
        currency=account.currency,
        is_active=account.is_active,
        unmatched_count=int(unmatched or 0),
        statement_balance_cents=_balance(db, account.id),
        last_statement_on=last.booked_on if last else None,
    )


def list_accounts(db: Session) -> list[BankAccountOut]:
    accounts = db.scalars(select(BankAccount).order_by(BankAccount.is_active.desc(), BankAccount.name))
    return [_account_out(db, account) for account in accounts]


def save_account(db: Session, data: BankAccountWrite, account_id: uuid.UUID | None = None) -> BankAccountOut:
    if account_id is None:
        account = BankAccount(currency=business_currency(db))
        db.add(account)
    else:
        account = _account(db, account_id)
    account.name = data.name.strip()
    account.bank = data.bank.strip()
    account.iban = data.iban
    account.is_active = data.is_active
    db.commit()
    return _account_out(db, account)


# --- Statements ----------------------------------------------------------------------------------


def _statement_out(statement: BankStatement, names: dict[uuid.UUID, str]) -> StatementOut:
    return StatementOut(
        id=statement.id,
        file_name=statement.file_name,
        file_format=statement.file_format,  # type: ignore[arg-type]
        period_from=statement.period_from,
        period_to=statement.period_to,
        lines_imported=statement.lines_imported,
        lines_skipped=statement.lines_skipped,
        imported_at=statement.created_at,
        imported_by_name=names.get(statement.imported_by_id) if statement.imported_by_id else None,
    )


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item}
    if not wanted:
        return {}
    return {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(wanted))).unique()}


def import_statement(
    db: Session, principal: Principal, account_id: uuid.UUID, file_name: str, content: bytes
) -> StatementImportOut:
    account = _account(db, account_id)
    if not account.is_active:
        raise ApiError(409, "account_inactive", "This bank account is archived.")
    file_format, parsed = parse(content, file_name)
    hashes = line_hashes(parsed)
    known = set(
        db.scalars(
            select(BankStatementLine.line_hash).where(
                BankStatementLine.account_id == account.id, BankStatementLine.line_hash.in_(hashes)
            )
        )
    )
    statement = BankStatement(
        account_id=account.id,
        file_name=file_name[:255],
        file_format=file_format,
        period_from=min(line.booked_on for line in parsed),
        period_to=max(line.booked_on for line in parsed),
        imported_by_id=_user_id(principal),
    )
    db.add(statement)
    db.flush()
    imported = 0
    for line, digest in zip(parsed, hashes, strict=True):
        if digest in known:
            continue
        db.add(
            BankStatementLine(
                account_id=account.id,
                statement_id=statement.id,
                booked_on=line.booked_on,
                description=line.description,
                reference=line.reference,
                amount_cents=line.amount_cents,
                balance_cents=line.balance_cents,
                line_hash=digest,
            )
        )
        imported += 1
    statement.lines_imported = imported
    statement.lines_skipped = len(parsed) - imported
    db.flush()
    matched = _auto_match(db, account.id)
    db.commit()
    return StatementImportOut(
        statement=_statement_out(statement, _names(db, {statement.imported_by_id})), auto_matched=matched
    )


def list_statements(db: Session, account_id: uuid.UUID) -> list[StatementOut]:
    _account(db, account_id)
    statements = list(
        db.scalars(
            select(BankStatement)
            .where(BankStatement.account_id == account_id)
            .order_by(BankStatement.created_at.desc())
            .limit(100)
        )
    )
    names = _names(db, {row.imported_by_id for row in statements})
    return [_statement_out(row, names) for row in statements]


def _line_out(line: BankStatementLine) -> StatementLineOut:
    return StatementLineOut(
        id=line.id,
        booked_on=line.booked_on,
        description=line.description,
        reference=line.reference,
        amount_cents=line.amount_cents,
        balance_cents=line.balance_cents,
        status=line.status,  # type: ignore[arg-type]
        matched_key=line.matched_key,
        matched_label=line.matched_label,
        fee_cents=line.fee_cents,
        auto_matched=line.status == "MATCHED" and line.matched_by_id is None,
        match_note=line.match_note,
    )


def list_lines(
    db: Session,
    account_id: uuid.UUID,
    *,
    status: str | None,
    start: date | None,
    end: date | None,
    offset: int,
    limit: int,
) -> tuple[list[StatementLineOut], int]:
    _account(db, account_id)
    query = select(BankStatementLine).where(BankStatementLine.account_id == account_id)
    if status:
        query = query.where(BankStatementLine.status == status)
    if start:
        query = query.where(BankStatementLine.booked_on >= start)
    if end:
        query = query.where(BankStatementLine.booked_on <= end)
    total = int(db.scalar(select(func.count()).select_from(query.subquery())) or 0)
    rows = db.scalars(
        query.order_by(BankStatementLine.booked_on.desc(), BankStatementLine.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_line_out(row) for row in rows], total


# --- Book side -----------------------------------------------------------------------------------


def book_items(db: Session, start: date, end: date) -> list[BookItem]:
    """Everything the books say moved through the bank between start and end (inclusive)."""
    since, until = _bounds(start, end)
    items: list[BookItem] = []
    stores = {row.id: row.code for row in db.scalars(select(Store))}

    settlements: dict[tuple[str, uuid.UUID, date], int] = defaultdict(int)
    tenders = db.execute(
        select(SaleTender, Sale)
        .join(Sale, SaleTender.sale_id == Sale.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED_SALES),
            SaleTender.method.in_(("card", "qr", "bnpl", "transfer")),
        )
    )
    for tender, sale in tenders:
        if tender.method == "transfer":
            items.append(
                BookItem(
                    key=f"tender:{tender.id}",
                    kind="TRANSFER_RECEIPT",
                    booked_on=_day(sale.created_at),
                    amount_cents=tender.amount_cents,
                    label=f"Transfer for {sale.invoice_number or sale.client_sale_id[:8].upper()}",
                    reference=tender.reference,
                    store_id=sale.store_id,
                )
            )
        else:
            settlements[(tender.method, sale.store_id, _day(sale.created_at))] += tender.amount_cents
    refunds = db.execute(
        select(ReturnTender, SaleReturn)
        .join(SaleReturn, ReturnTender.return_id == SaleReturn.id)
        .where(
            SaleReturn.created_at >= since,
            SaleReturn.created_at < until,
            ReturnTender.method.in_(("original_card", "original_bnpl")),
        )
    )
    for tender, record in refunds:
        method = "bnpl" if tender.method == "original_bnpl" else "card"
        settlements[(method, record.store_id, _day(record.created_at))] -= tender.amount_cents
    for (method, store_id, day), amount in settlements.items():
        if amount <= 0:
            continue
        kind, name = SETTLEMENT_OF_METHOD[method]
        items.append(
            BookItem(
                key=f"{method}:{store_id}:{day.isoformat()}",
                kind=kind,
                booked_on=day,
                amount_cents=amount,
                label=f"{name} takings {stores.get(store_id, '')} {day.isoformat()}",
                store_id=store_id,
            )
        )

    receipts = db.scalars(
        select(CustomerLedgerEntry).where(
            CustomerLedgerEntry.entry_type == "PAYMENT",
            CustomerLedgerEntry.sale_id.is_(None),
            CustomerLedgerEntry.method == "transfer",
            CustomerLedgerEntry.created_at >= since,
            CustomerLedgerEntry.created_at < until,
        )
    )
    for entry in receipts:
        items.append(
            BookItem(
                key=f"receipt:{entry.id}",
                kind="ACCOUNT_RECEIPT",
                booked_on=_day(entry.created_at),
                amount_cents=-entry.amount_cents,
                label="Account payment received",
                reference=entry.reference,
            )
        )

    cheques = db.scalars(
        select(Cheque).where(
            Cheque.status.in_(("DEPOSITED", "CLEARED")), Cheque.cheque_date >= start, Cheque.cheque_date <= end
        )
    )
    for cheque in cheques:
        items.append(
            BookItem(
                key=f"cheque:{cheque.id}",
                kind="CHEQUE_DEPOSIT",
                booked_on=cheque.cheque_date,
                amount_cents=cheque.amount_cents,
                label=f"Cheque {cheque.cheque_number} ({cheque.bank})",
                reference=cheque.cheque_number,
                store_id=cheque.store_id,
            )
        )

    suppliers = {row.id: row.name for row in db.scalars(select(Supplier))}
    payments = db.scalars(
        select(SupplierPayment).where(
            SupplierPayment.paid_on >= start,
            SupplierPayment.paid_on <= end,
            SupplierPayment.status != "VOID",
            SupplierPayment.method.in_(("transfer", "card", "cheque")),
        )
    )
    for payment in payments:
        if payment.method == "cheque" and payment.status != "CLEARED":
            continue
        when = payment.paid_on
        if payment.method == "cheque":
            when = payment.cheque_date or payment.paid_on
        items.append(
            BookItem(
                key=f"supplier_payment:{payment.id}",
                kind="SUPPLIER_PAYMENT",
                booked_on=when,
                amount_cents=-payment.amount_cents,
                label=f"Payment to {suppliers.get(payment.supplier_id, 'supplier')}",
                reference=payment.cheque_number or payment.reference,
            )
        )

    expenses = db.scalars(
        select(Expense).where(
            Expense.spent_on >= start,
            Expense.spent_on <= end,
            Expense.status == "RECORDED",
            Expense.paid_from.in_(("BANK", "CARD")),
        )
    )
    for expense in expenses:
        if expense.reference.startswith(FEE_REFERENCE):
            continue
        items.append(
            BookItem(
                key=f"expense:{expense.id}",
                kind="EXPENSE",
                booked_on=expense.spent_on,
                amount_cents=-expense.total_cents,
                label=f"{expense.number} {expense.payee or expense.description}".strip(),
                reference=expense.reference,
                store_id=expense.store_id,
            )
        )

    topups = db.scalars(
        select(PettyCashEntry).where(
            PettyCashEntry.kind == "TOPUP",
            PettyCashEntry.source == "bank",
            PettyCashEntry.created_at >= since,
            PettyCashEntry.created_at < until,
        )
    )
    for entry in topups:
        items.append(
            BookItem(
                key=f"petty:{entry.id}",
                kind="PETTY_CASH_TOPUP",
                booked_on=_day(entry.created_at),
                amount_cents=-entry.amount_cents,
                label=f"Petty cash top-up {stores.get(entry.store_id, '')}".strip(),
                store_id=entry.store_id,
            )
        )

    for run in staff_service.finalized_in(db, since, until):
        net = sum(line.net_cents for line in run.lines)
        if net:
            items.append(
                BookItem(
                    key=f"payroll:{run.id}",
                    kind="PAYROLL",
                    booked_on=_day(run.finalized_at),  # type: ignore[arg-type]
                    amount_cents=-net,
                    label=f"Payroll {run.year}-{run.month:02d} (WPS)",
                )
            )
    return items


def _matched_keys(db: Session) -> set[str]:
    return set(
        db.scalars(select(BankStatementLine.matched_key).where(BankStatementLine.matched_key.is_not(None))).all()
    )


def _item_out(item: BookItem, stores: dict[uuid.UUID, str]) -> BookItemOut:
    return BookItemOut(
        key=item.key,
        kind=item.kind,  # type: ignore[arg-type]
        booked_on=item.booked_on,
        amount_cents=item.amount_cents,
        label=item.label,
        reference=item.reference,
        store_code=stores.get(item.store_id) if item.store_id else None,
    )


def _in_window(line: BankStatementLine, item: BookItem) -> bool:
    before, after = WINDOWS[item.kind]
    return item.booked_on - timedelta(days=before) <= line.booked_on <= item.booked_on + timedelta(days=after)


def _reference_hit(line: BankStatementLine, item: BookItem) -> bool:
    ref = item.reference.strip().lower()
    if len(ref) < 4:
        return False
    return ref in line.description.lower() or ref in line.reference.lower()


def _score(line: BankStatementLine, item: BookItem, fee_limit_bps: int) -> tuple[int, int] | None:
    """(score, fee) when the line could be this book item, else None."""
    if (line.amount_cents > 0) != (item.amount_cents > 0) or not _in_window(line, item):
        return None
    days = abs((line.booked_on - item.booked_on).days)
    bonus = 25 if _reference_hit(line, item) else 0
    if line.amount_cents == item.amount_cents:
        return 100 - days + bonus, 0
    fee = item.amount_cents - line.amount_cents
    if item.kind in SETTLEMENT_KINDS and 0 < fee <= item.amount_cents * fee_limit_bps // 10_000:
        return 60 - days + bonus, fee
    return None


def _window_for(lines: list[BankStatementLine]) -> tuple[date, date]:
    first = min(line.booked_on for line in lines)
    last = max(line.booked_on for line in lines)
    return first - timedelta(days=LOOKBACK_DAYS), last + timedelta(days=5)


def _apply_match(
    db: Session,
    line: BankStatementLine,
    item: BookItem,
    fee: int,
    user_id: uuid.UUID | None,
    note: str = "",
) -> None:
    line.status = "MATCHED"
    line.matched_key = item.key
    line.matched_label = item.label[:160]
    line.fee_cents = fee
    line.matched_by_id = user_id
    line.match_note = note
    if fee and item.store_id is not None:
        expense = Expense(
            number=next_server_number(db, item.store_id, "EXP"),
            store_id=item.store_id,
            category="BANK_FEES",
            description=f"Card terminal fee: {item.label}"[:200],
            payee="Card acquirer",
            spent_on=line.booked_on,
            net_cents=fee,
            tax_cents=0,
            total_cents=fee,
            currency=business_currency(db),
            has_tax_invoice=False,
            paid_from="BANK",
            reference=f"{FEE_REFERENCE}:{str(line.id)[:8]}",
            created_by_id=user_id,
        )
        db.add(expense)
        db.flush()
        line.fee_expense_id = expense.id


def _auto_match(db: Session, account_id: uuid.UUID) -> int:
    lines = list(
        db.scalars(
            select(BankStatementLine)
            .where(BankStatementLine.account_id == account_id, BankStatementLine.status == "UNMATCHED")
            .order_by(BankStatementLine.booked_on, BankStatementLine.created_at)
        )
    )
    if not lines:
        return 0
    start, end = _window_for(lines)
    taken = _matched_keys(db)
    pool = [item for item in book_items(db, start, end) if item.key not in taken]
    matched = 0
    for line in lines:
        scored = []
        for item in pool:
            if item.key in taken:
                continue
            result = _score(line, item, AUTO_FEE_BPS)
            if result is not None:
                scored.append((result[0], result[1], item))
        if not scored:
            continue
        scored.sort(key=lambda row: row[0], reverse=True)
        best = scored[0]
        if best[0] < 50 or (len(scored) > 1 and scored[1][0] == best[0]):
            continue
        _apply_match(db, line, best[2], best[1], None)
        taken.add(best[2].key)
        matched += 1
    db.flush()
    return matched


def auto_match(db: Session, account_id: uuid.UUID) -> AutoMatchOut:
    _account(db, account_id)
    matched = _auto_match(db, account_id)
    db.commit()
    return AutoMatchOut(matched=matched)


def _line(db: Session, line_id: uuid.UUID) -> BankStatementLine:
    line = db.get(BankStatementLine, line_id)
    if line is None:
        raise ApiError(404, "not_found", "Statement line was not found.")
    return line


def candidates(db: Session, line_id: uuid.UUID) -> list[CandidateOut]:
    line = _line(db, line_id)
    start, end = _window_for([line])
    taken = _matched_keys(db)
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    rows: list[CandidateOut] = []
    for item in book_items(db, start, end):
        if item.key in taken:
            continue
        result = _score(line, item, MANUAL_FEE_BPS)
        if result is None:
            continue
        rows.append(CandidateOut(**_item_out(item, stores).model_dump(), score=result[0], fee_cents=result[1]))
    rows.sort(key=lambda row: row.score, reverse=True)
    return rows[:25]


def match(db: Session, principal: Principal, line_id: uuid.UUID, key: str, note: str) -> StatementLineOut:
    line = _line(db, line_id)
    if line.status != "UNMATCHED":
        raise ApiError(409, "line_not_open", "Unmatch or restore this line before matching it again.")
    if key in _matched_keys(db):
        raise ApiError(409, "already_matched", "That book entry is already matched to another statement line.")
    start, end = _window_for([line])
    item = next((row for row in book_items(db, start, end) if row.key == key), None)
    if item is None:
        raise ApiError(404, "not_found", "That book entry was not found near this statement date.")
    if (line.amount_cents > 0) != (item.amount_cents > 0):
        raise ApiError(422, "direction_mismatch", "Money in can only match a receipt, money out only a payment.")
    fee = 0
    if line.amount_cents != item.amount_cents:
        fee = item.amount_cents - line.amount_cents
        allowed = item.kind in SETTLEMENT_KINDS and 0 < fee <= item.amount_cents * MANUAL_FEE_BPS // 10_000
        if not allowed:
            raise ApiError(
                422,
                "amount_mismatch",
                "The amounts differ. Only card and QR settlements can be short, by the terminal fee (up to 10%).",
            )
    _apply_match(db, line, item, fee, _user_id(principal), note.strip())
    db.commit()
    return _line_out(line)


def book_charge(db: Session, principal: Principal, line_id: uuid.UUID, store_id: uuid.UUID | None) -> StatementLineOut:
    """A bank charge seen only on the statement: record it as a bank-fee expense and match the line to it."""
    line = _line(db, line_id)
    if line.status != "UNMATCHED":
        raise ApiError(409, "line_not_open", "Unmatch or restore this line before matching it again.")
    if line.amount_cents >= 0:
        raise ApiError(422, "not_a_charge", "Only money out of the account can be booked as a bank charge.")
    store = db.get(Store, store_id) if store_id else None
    if store is None:
        store = db.scalars(select(Store).order_by(Store.is_warehouse, Store.code).limit(1)).first()
    if store is None:
        raise ApiError(422, "no_store", "Add a branch before booking bank charges.")
    expense = Expense(
        number=next_server_number(db, store.id, "EXP"),
        store_id=store.id,
        category="BANK_FEES",
        description=(line.description or "Bank charge")[:200],
        payee="Bank",
        spent_on=line.booked_on,
        net_cents=-line.amount_cents,
        tax_cents=0,
        total_cents=-line.amount_cents,
        currency=business_currency(db),
        has_tax_invoice=False,
        paid_from="BANK",
        reference=f"{FEE_REFERENCE}:{str(line.id)[:8]}",
        created_by_id=_user_id(principal),
    )
    db.add(expense)
    db.flush()
    line.status = "MATCHED"
    line.matched_key = f"expense:{expense.id}"
    line.matched_label = f"{expense.number} bank charge"
    line.fee_expense_id = expense.id
    line.matched_by_id = _user_id(principal)
    line.match_note = "Booked as a bank charge"
    db.commit()
    return _line_out(line)


def unmatch(db: Session, principal: Principal, line_id: uuid.UUID) -> StatementLineOut:
    line = _line(db, line_id)
    if line.status == "UNMATCHED":
        return _line_out(line)
    if line.fee_expense_id is not None:
        db.execute(
            update(Expense)
            .where(Expense.id == line.fee_expense_id)
            .values(status="VOID", voided_by_id=_user_id(principal), void_reason="Bank line unmatched")
        )
    line.status = "UNMATCHED"
    line.matched_key = None
    line.matched_label = ""
    line.fee_cents = 0
    line.fee_expense_id = None
    line.matched_by_id = None
    line.match_note = ""
    db.commit()
    return _line_out(line)


def ignore(db: Session, principal: Principal, line_id: uuid.UUID, note: str) -> StatementLineOut:
    line = _line(db, line_id)
    if line.status != "UNMATCHED":
        raise ApiError(409, "line_not_open", "Only unmatched lines can be set aside.")
    line.status = "IGNORED"
    line.matched_by_id = _user_id(principal)
    line.match_note = note.strip()
    db.commit()
    return _line_out(line)


def summary(db: Session, account_id: uuid.UUID) -> ReconciliationSummary:
    _account(db, account_id)
    rows = list(db.scalars(select(BankStatementLine).where(BankStatementLine.account_id == account_id)))
    counts = defaultdict(int)
    for row in rows:
        counts[row.status] += 1
    period_from = min((row.booked_on for row in rows), default=None)
    period_to = max((row.booked_on for row in rows), default=None)
    outstanding: list[BookItemOut] = []
    if period_from and period_to:
        taken = _matched_keys(db)
        stores = {row.id: row.code for row in db.scalars(select(Store))}
        cutoff = period_to - timedelta(days=3)
        for item in book_items(db, period_from, period_to):
            if item.key not in taken and item.booked_on <= cutoff:
                outstanding.append(_item_out(item, stores))
        outstanding.sort(key=lambda row: row.booked_on)
    return ReconciliationSummary(
        account_id=account_id,
        lines=len(rows),
        matched=counts["MATCHED"],
        unmatched=counts["UNMATCHED"],
        ignored=counts["IGNORED"],
        unmatched_in_cents=sum(r.amount_cents for r in rows if r.status == "UNMATCHED" and r.amount_cents > 0),
        unmatched_out_cents=-sum(r.amount_cents for r in rows if r.status == "UNMATCHED" and r.amount_cents < 0),
        fees_cents=sum(row.fee_cents for row in rows),
        statement_balance_cents=_balance(db, account_id),
        period_from=period_from,
        period_to=period_to,
        outstanding=outstanding[:200],
    )
