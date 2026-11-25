"""Tenant expense categories. The original codes stay attached to historical expenses."""

from __future__ import annotations

import re
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.expense import Expense, ExpenseCategory
from app.schemas.expenses import ExpenseCategoryOut

DEFAULT_CATEGORIES: tuple[tuple[str, str, int], ...] = (
    ("RENT", "Rent", 10),
    ("UTILITIES", "Utilities & telecom", 20),
    ("SALARIES", "Salaries & wages", 30),
    ("TRANSPORT", "Transport & fuel", 40),
    ("MARKETING", "Marketing", 50),
    ("MAINTENANCE", "Repairs & maintenance", 60),
    ("OFFICE", "Office & supplies", 70),
    ("BANK_FEES", "Bank & card fees", 80),
    ("OTHER", "Other", 90),
)

LABELS = {code: name for code, name, _order in DEFAULT_CATEGORIES}


def name_key(name: str) -> str:
    return " ".join(name.split()).lower()


def ensure_categories(db: Session) -> None:
    present = {row.code for row in db.scalars(select(ExpenseCategory))}
    missing = [item for item in DEFAULT_CATEGORIES if item[0] not in present]
    for code, name, order in missing:
        db.add(
            ExpenseCategory(
                code=code,
                name=name,
                name_key=name_key(name),
                description="",
                sort_order=order,
                is_active=True,
            )
        )
    if missing:
        db.flush()
    linked = _link_legacy(db)
    if missing or linked:
        db.commit()


def _link_legacy(db: Session) -> bool:
    pending = list(db.scalars(select(Expense).where(Expense.category_id.is_(None)).limit(500)))
    if not pending:
        return False
    by_code = {row.code: row.id for row in db.scalars(select(ExpenseCategory))}
    changed = False
    for expense in pending:
        match = by_code.get(expense.category)
        if match is not None:
            expense.category_id = match
            changed = True
    if changed:
        db.flush()
    return changed


def list_categories(db: Session, *, active_only: bool) -> list[ExpenseCategoryOut]:
    ensure_categories(db)
    statement = select(ExpenseCategory).order_by(ExpenseCategory.sort_order, ExpenseCategory.name)
    if active_only:
        statement = statement.where(ExpenseCategory.is_active.is_(True))
    return [_out(row) for row in db.scalars(statement)]


def resolve(db: Session, *, category_id: uuid.UUID | None, code: str | None) -> ExpenseCategory:
    ensure_categories(db)
    row: ExpenseCategory | None
    if category_id is not None:
        row = db.get(ExpenseCategory, category_id)
        if row is None:
            raise ApiError(422, "category_invalid", "Select an expense category.")
    else:
        row = db.scalar(select(ExpenseCategory).where(ExpenseCategory.code == (code or "").strip().upper()))
        if row is None:
            raise ApiError(422, "category_invalid", "Select an expense category.")
    if not row.is_active:
        raise ApiError(422, "category_inactive", "That expense category is no longer offered. Choose another.")
    return row


def create_category(db: Session, principal: Principal, name: str, description: str) -> ExpenseCategoryOut:
    ensure_categories(db)
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ApiError(422, "category_name", "Enter an expense category name.")
    if len(cleaned) > 80:
        raise ApiError(422, "category_name", "Keep the category name to 80 characters.")
    key = name_key(cleaned)
    existing = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name_key == key))
    actor = principal.user.id if principal.user else None
    if existing is not None:
        if not existing.is_active:
            existing.is_active = True
            existing.updated_by_id = actor
            db.commit()
        return _out(existing)
    code = _code(db, cleaned)
    row = ExpenseCategory(
        code=code,
        name=cleaned,
        name_key=key,
        description=description.strip()[:200],
        is_active=True,
        sort_order=200,
        created_by_id=actor,
        updated_by_id=actor,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        again = db.scalar(select(ExpenseCategory).where(ExpenseCategory.name_key == key))
        if again is None:
            raise
        return _out(again)
    return _out(row)


def deactivate(db: Session, principal: Principal, category_id: uuid.UUID) -> ExpenseCategoryOut:
    ensure_categories(db)
    row = db.get(ExpenseCategory, category_id)
    if row is None:
        raise ApiError(404, "not_found", "Expense category was not found.")
    row.is_active = False
    row.updated_by_id = principal.user.id if principal.user else None
    db.commit()
    return _out(row)


def names_for(db: Session, ids: set[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    wanted = {item for item in ids if item}
    if not wanted:
        return {}
    return {row.id: row.name for row in db.scalars(select(ExpenseCategory).where(ExpenseCategory.id.in_(wanted)))}


def _code(db: Session, name: str) -> str:
    base = re.sub(r"[^A-Z0-9]+", "_", name.upper()).strip("_")[:24] or "CUSTOM"
    code, suffix = base, 2
    while db.scalar(select(ExpenseCategory.id).where(ExpenseCategory.code == code)) is not None:
        code = f"{base[:24]}_{suffix}"
        suffix += 1
    return code[:32]


def _out(row: ExpenseCategory) -> ExpenseCategoryOut:
    return ExpenseCategoryOut(
        id=row.id,
        code=row.code,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        sort_order=row.sort_order,
    )
