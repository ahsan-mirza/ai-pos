"""Expenses (rent, utilities, fuel, ...) and the per-branch petty cash float that pays the small ones."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.expense import Expense, PettyCashEntry
from app.models.store import Store
from app.models.user import User
from app.schemas.expenses import (
    CategoryTotal,
    ExpenseCreate,
    ExpenseList,
    ExpenseOut,
    PettyCashCount,
    PettyCashEntryOut,
    PettyCashOut,
    PettyCashTopUp,
)
from app.services.numbering import next_server_number
from app.services.settings_service import business_currency, cached_settings
from app.services.tax import div_half_up
from app.services.tax import policy as tax_policy_for


def recoverable_tax(expense: Expense, vat_registered: bool) -> int:
    return expense.tax_cents if vat_registered and expense.has_tax_invoice else 0


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only record expenses for your own branch.")


def _user_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user else None


def _names(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item}
    if not wanted:
        return {}
    return {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(wanted))).unique()}


def _out(expense: Expense, stores: dict[uuid.UUID, str], names: dict[uuid.UUID, str], registered: bool) -> ExpenseOut:
    return ExpenseOut(
        id=expense.id,
        number=expense.number,
        store_id=expense.store_id,
        store_code=stores.get(expense.store_id, ""),
        category=expense.category,  # type: ignore[arg-type]
        description=expense.description,
        payee=expense.payee,
        payee_trn=expense.payee_trn,
        spent_on=expense.spent_on,
        net_cents=expense.net_cents,
        tax_cents=expense.tax_cents,
        recoverable_tax_cents=recoverable_tax(expense, registered),
        total_cents=expense.total_cents,
        currency=expense.currency,
        has_tax_invoice=expense.has_tax_invoice,
        paid_from=expense.paid_from,  # type: ignore[arg-type]
        reference=expense.reference,
        status=expense.status,  # type: ignore[arg-type]
        created_by_name=names.get(expense.created_by_id) if expense.created_by_id else None,
        void_reason=expense.void_reason,
    )


def _petty_balance(db: Session, store_id: uuid.UUID) -> int:
    last = db.scalar(
        select(PettyCashEntry.balance_after)
        .where(PettyCashEntry.store_id == store_id)
        .order_by(PettyCashEntry.created_at.desc(), PettyCashEntry.id.desc())
        .limit(1)
    )
    return int(last or 0)


def _petty(db: Session, store_id: uuid.UUID, kind: str, amount: int, **extra) -> PettyCashEntry:
    balance = _petty_balance(db, store_id) + amount
    entry = PettyCashEntry(store_id=store_id, kind=kind, amount_cents=amount, balance_after=balance, **extra)
    db.add(entry)
    db.flush()
    return entry


def record(db: Session, principal: Principal, data: ExpenseCreate) -> ExpenseOut:
    _scope(principal, data.store_id)
    store = db.get(Store, data.store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    if data.tax_cents is not None:
        tax = data.tax_cents
    else:
        rate = tax_policy_for(db).rate_for(data.tax_category)
        tax = div_half_up(data.total_cents * rate, 10_000 + rate)
    if data.has_tax_invoice and tax and not data.payee_trn:
        raise ApiError(422, "trn_required", "A tax invoice shows the supplier's TRN; enter it to recover the VAT.")
    if data.paid_from == "PETTY_CASH":
        balance = _petty_balance(db, store.id)
        if balance < data.total_cents:
            raise ApiError(
                422, "petty_cash_short", f"Petty cash at {store.code} holds {balance / 100:,.2f}; top it up first."
            )
    expense = Expense(
        number=next_server_number(db, store.id, "EXP"),
        store_id=store.id,
        category=data.category,
        description=data.description.strip(),
        payee=data.payee.strip(),
        payee_trn=data.payee_trn,
        spent_on=data.spent_on,
        net_cents=data.total_cents - tax,
        tax_cents=tax,
        total_cents=data.total_cents,
        currency=business_currency(db),
        has_tax_invoice=data.has_tax_invoice,
        paid_from=data.paid_from,
        reference=data.reference.strip(),
        created_by_id=_user_id(principal),
    )
    db.add(expense)
    db.flush()
    if data.paid_from == "PETTY_CASH":
        _petty(
            db,
            store.id,
            "EXPENSE",
            -data.total_cents,
            expense_id=expense.id,
            note=expense.description[:255],
            user_id=_user_id(principal),
        )
    db.commit()
    return _out(
        expense, {store.id: store.code}, _names(db, {expense.created_by_id}), cached_settings(db).vat_registered
    )


def void(db: Session, principal: Principal, expense_id: uuid.UUID, reason: str) -> ExpenseOut:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise ApiError(404, "not_found", "Expense was not found.")
    _scope(principal, expense.store_id)
    if expense.status == "VOID":
        raise ApiError(409, "already_void", f"Expense {expense.number} is already void.")
    expense.status = "VOID"
    expense.voided_by_id = _user_id(principal)
    expense.void_reason = reason.strip()
    if expense.paid_from == "PETTY_CASH":
        _petty(
            db,
            expense.store_id,
            "VOID",
            expense.total_cents,
            expense_id=expense.id,
            note=f"Voided {expense.number}: {reason.strip()}"[:255],
            user_id=_user_id(principal),
        )
    db.commit()
    store = db.get(Store, expense.store_id)
    return _out(
        expense,
        {expense.store_id: store.code if store else ""},
        _names(db, {expense.created_by_id}),
        cached_settings(db).vat_registered,
    )


def list_expenses(
    db: Session,
    principal: Principal,
    *,
    start: date,
    end: date,
    store_id: uuid.UUID | None,
    category: str | None,
) -> ExpenseList:
    query = (
        select(Expense)
        .where(Expense.spent_on >= start, Expense.spent_on <= end)
        .order_by(Expense.spent_on.desc(), Expense.created_at.desc())
    )
    scope = principal.store_id or store_id
    if scope is not None:
        query = query.where(Expense.store_id == scope)
    if category is not None:
        query = query.where(Expense.category == category)
    rows = list(db.scalars(query.limit(1000)))
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    names = _names(db, {row.created_by_id for row in rows})
    registered = cached_settings(db).vat_registered
    live = [row for row in rows if row.status != "VOID"]
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in live:
        totals[row.category][0] += row.total_cents
        totals[row.category][1] += 1
    return ExpenseList(
        items=[_out(row, stores, names, registered) for row in rows],
        total_cents=sum(row.total_cents for row in live),
        recoverable_tax_cents=sum(recoverable_tax(row, registered) for row in live),
        by_category=sorted(
            (CategoryTotal(category=key, total_cents=value[0], count=value[1]) for key, value in totals.items()),  # type: ignore[arg-type]
            key=lambda row: -row.total_cents,
        ),
    )


def petty_cash(db: Session, principal: Principal, store_id: uuid.UUID) -> PettyCashOut:
    _scope(principal, store_id)
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    entries = list(
        db.scalars(
            select(PettyCashEntry)
            .where(PettyCashEntry.store_id == store_id)
            .order_by(PettyCashEntry.created_at.desc(), PettyCashEntry.id.desc())
            .limit(100)
        )
    )
    numbers = {
        row.id: row.number
        for row in db.scalars(select(Expense).where(Expense.id.in_({e.expense_id for e in entries if e.expense_id})))
    }
    names = _names(db, {entry.user_id for entry in entries})
    return PettyCashOut(
        store_id=store.id,
        store_code=store.code,
        balance_cents=_petty_balance(db, store.id),
        entries=[
            PettyCashEntryOut(
                id=entry.id,
                kind=entry.kind,  # type: ignore[arg-type]
                amount_cents=entry.amount_cents,
                balance_after=entry.balance_after,
                expense_number=numbers.get(entry.expense_id) if entry.expense_id else None,
                note=entry.note,
                user_name=names.get(entry.user_id) if entry.user_id else None,
                created_at=entry.created_at if entry.created_at.tzinfo else entry.created_at.replace(tzinfo=UTC),
            )
            for entry in entries
        ],
    )


def top_up(db: Session, principal: Principal, data: PettyCashTopUp) -> PettyCashOut:
    _scope(principal, data.store_id)
    if db.get(Store, data.store_id) is None:
        raise ApiError(404, "not_found", "Store was not found.")
    _petty(
        db,
        data.store_id,
        "TOPUP",
        data.amount_cents,
        source=data.source,
        note=data.note.strip() or f"Top-up from the {data.source}",
        user_id=_user_id(principal),
    )
    db.commit()
    return petty_cash(db, principal, data.store_id)


def count(db: Session, principal: Principal, data: PettyCashCount) -> PettyCashOut:
    """Sets the float to what was counted; the difference is booked as a COUNT entry."""
    _scope(principal, data.store_id)
    difference = data.counted_cents - _petty_balance(db, data.store_id)
    if difference == 0:
        raise ApiError(422, "no_change", "The count matches the book balance.")
    _petty(db, data.store_id, "COUNT", difference, note=data.note.strip(), user_id=_user_id(principal))
    db.commit()
    return petty_cash(db, principal, data.store_id)


def petty_cash_moves(db: Session, since: datetime, until: datetime) -> list[PettyCashEntry]:
    """Top-ups and count corrections in a period, for the journal export."""
    return list(
        db.scalars(
            select(PettyCashEntry).where(
                PettyCashEntry.kind.in_(("TOPUP", "COUNT")),
                PettyCashEntry.created_at >= since,
                PettyCashEntry.created_at < until,
            )
        )
    )


def period_expenses(db: Session, start: date, end: date, store_id: uuid.UUID | None) -> list[Expense]:
    query = select(Expense).where(Expense.spent_on >= start, Expense.spent_on <= end, Expense.status != "VOID")
    if store_id is not None:
        query = query.where(Expense.store_id == store_id)
    return list(db.scalars(query))
