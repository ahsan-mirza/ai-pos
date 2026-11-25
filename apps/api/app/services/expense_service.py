"""Expenses (rent, utilities, fuel, ...) and the per-branch petty cash float that pays the small ones."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.batch import Supplier
from app.models.expense import Expense, PettyCashEntry
from app.models.store import Store
from app.models.user import User
from app.schemas.expenses import (
    CategoryTotal,
    ExpenseCreate,
    ExpenseList,
    ExpenseOut,
    ExpenseSupplier,
    PettyCashCount,
    PettyCashEntryOut,
    PettyCashOut,
    PettyCashTopUp,
)
from app.services import expense_bills, expense_catalog
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


def _supplier_labels(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, tuple[str, str]]:
    wanted = {item for item in ids if item}
    if not wanted:
        return {}
    return {row.id: (row.name, row.code) for row in db.scalars(select(Supplier).where(Supplier.id.in_(wanted)))}


def _chosen_supplier(db: Session, supplier_id: uuid.UUID | None) -> Supplier | None:
    if supplier_id is None:
        return None
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ApiError(422, "supplier_invalid", "Select a valid supplier or clear the supplier selection.")
    if not supplier.is_active:
        raise ApiError(422, "supplier_inactive", "That supplier is inactive. Choose another supplier.")
    return supplier


def search_suppliers(db: Session, query: str | None) -> list[ExpenseSupplier]:
    statement = select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name).limit(50)
    text = (query or "").strip().lower()
    if text:
        like = f"%{text}%"
        statement = statement.where(
            or_(
                func.lower(Supplier.name).like(like),
                func.lower(Supplier.code).like(like),
                func.lower(func.coalesce(Supplier.phone, "")).like(like),
                func.lower(func.coalesce(Supplier.trn, "")).like(like),
            )
        )
    return [
        ExpenseSupplier(id=row.id, name=row.name, code=row.code, phone=row.phone, trn=row.trn, is_active=row.is_active)
        for row in db.scalars(statement)
    ]


def _out(
    expense: Expense,
    stores: dict[uuid.UUID, str],
    names: dict[uuid.UUID, str],
    registered: bool,
    suppliers: dict[uuid.UUID, tuple[str, str]],
    categories: dict[uuid.UUID, str],
    bills: set[uuid.UUID],
) -> ExpenseOut:
    supplier_name, supplier_code = suppliers.get(expense.supplier_id, ("", "")) if expense.supplier_id else ("", "")
    category_name = categories.get(expense.category_id, "") if expense.category_id else ""
    return ExpenseOut(
        id=expense.id,
        number=expense.number,
        store_id=expense.store_id,
        store_code=stores.get(expense.store_id, ""),
        category=expense.category,
        category_id=expense.category_id,
        category_name=category_name or expense_catalog.LABELS.get(expense.category, expense.category),
        description=expense.description,
        payee=expense.payee,
        payee_trn=expense.payee_trn,
        supplier_id=expense.supplier_id,
        supplier_name=supplier_name,
        supplier_code=supplier_code,
        spent_on=expense.spent_on,
        net_cents=expense.net_cents,
        tax_cents=expense.tax_cents,
        recoverable_tax_cents=recoverable_tax(expense, registered),
        total_cents=expense.total_cents,
        currency=expense.currency,
        has_tax_invoice=expense.has_tax_invoice,
        has_bill=expense.id in bills,
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
    if data.client_key:
        existing = db.scalar(select(Expense).where(Expense.client_key == data.client_key))
        if existing is not None:
            _scope(principal, existing.store_id)
            store = db.get(Store, existing.store_id)
            return _out(
                existing,
                {existing.store_id: store.code if store else ""},
                _names(db, {existing.created_by_id}),
                cached_settings(db).vat_registered,
                _supplier_labels(db, {existing.supplier_id}),
                expense_catalog.names_for(db, {existing.category_id}),
                expense_bills.bill_ids(db, {existing.id}),
            )
    store = db.get(Store, data.store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    if data.tax_cents is not None:
        tax = data.tax_cents
    else:
        rate = tax_policy_for(db).rate_for(data.tax_category)
        tax = div_half_up(data.total_cents * rate, 10_000 + rate)
    category = expense_catalog.resolve(db, category_id=data.category_id, code=data.category)
    supplier = _chosen_supplier(db, data.supplier_id)
    payee = data.payee.strip() or (supplier.name if supplier is not None else "")
    payee_trn = data.payee_trn or (supplier.trn if supplier is not None and supplier.trn else None)
    if data.has_tax_invoice and tax and not payee_trn:
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
        category=category.code,
        category_id=category.id,
        description=data.description.strip(),
        payee=payee,
        payee_trn=payee_trn,
        supplier_id=supplier.id if supplier is not None else None,
        spent_on=data.spent_on,
        net_cents=data.total_cents - tax,
        tax_cents=tax,
        total_cents=data.total_cents,
        currency=business_currency(db),
        has_tax_invoice=data.has_tax_invoice,
        paid_from=data.paid_from,
        reference=data.reference.strip(),
        client_key=data.client_key,
        created_by_id=_user_id(principal),
    )
    db.add(expense)
    bill_path = None
    try:
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
        if data.bill is not None:
            bill_path = expense_bills.store(db, expense, data.bill, _user_id(principal))
        db.commit()
    except Exception:
        db.rollback()
        expense_bills.discard(bill_path)
        raise
    return _out(
        expense,
        {store.id: store.code},
        _names(db, {expense.created_by_id}),
        cached_settings(db).vat_registered,
        _supplier_labels(db, {expense.supplier_id}),
        expense_catalog.names_for(db, {expense.category_id}),
        expense_bills.bill_ids(db, {expense.id}),
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
        _supplier_labels(db, {expense.supplier_id}),
        expense_catalog.names_for(db, {expense.category_id}),
        expense_bills.bill_ids(db, {expense.id}),
    )


def list_expenses(
    db: Session,
    principal: Principal,
    *,
    start: date,
    end: date,
    store_id: uuid.UUID | None,
    category: str | None,
    supplier_id: uuid.UUID | None = None,
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
    if supplier_id is not None:
        query = query.where(Expense.supplier_id == supplier_id)
    expense_catalog.ensure_categories(db)
    rows = list(db.scalars(query.limit(1000)))
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    names = _names(db, {row.created_by_id for row in rows})
    suppliers = _supplier_labels(db, {row.supplier_id for row in rows})
    categories = expense_catalog.names_for(db, {row.category_id for row in rows})
    bills = expense_bills.bill_ids(db, {row.id for row in rows})
    registered = cached_settings(db).vat_registered
    live = [row for row in rows if row.status != "VOID"]
    totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    labels: dict[str, str] = {}
    for row in live:
        totals[row.category][0] += row.total_cents
        totals[row.category][1] += 1
        labels[row.category] = categories.get(row.category_id, "") if row.category_id else ""
        if not labels[row.category]:
            labels[row.category] = expense_catalog.LABELS.get(row.category, row.category)
    return ExpenseList(
        items=[_out(row, stores, names, registered, suppliers, categories, bills) for row in rows],
        total_cents=sum(row.total_cents for row in live),
        recoverable_tax_cents=sum(recoverable_tax(row, registered) for row in live),
        by_category=sorted(
            (
                CategoryTotal(category=key, category_name=labels.get(key, key), total_cents=value[0], count=value[1])
                for key, value in totals.items()
            ),
            key=lambda row: -row.total_cents,
        ),
    )


def get_expense(db: Session, principal: Principal, expense_id: uuid.UUID) -> Expense:
    expense = db.get(Expense, expense_id)
    if expense is None:
        raise ApiError(404, "not_found", "Expense was not found.")
    _scope(principal, expense.store_id)
    return expense


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
