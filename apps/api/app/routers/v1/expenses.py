import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import REGISTER_SCOPES, Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.expenses import (
    ExpenseBillOut,
    ExpenseCategory,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    ExpenseCreate,
    ExpenseList,
    ExpenseOut,
    ExpenseSupplier,
    ExpenseVoid,
    PettyCashCount,
    PettyCashOut,
    PettyCashTopUp,
)
from app.schemas.batches import SupplierCreate, SupplierOut
from app.services import expense_bills, expense_catalog, expense_service, import_batch_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.EXPENSES_MANAGE, scopes=REGISTER_SCOPES))]


@router.get("", response_model=ExpenseList)
def list_expenses(
    db: Db,
    principal: CanManage,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
    category: ExpenseCategory | None = None,
    supplier_id: uuid.UUID | None = None,
) -> ExpenseList:
    return expense_service.list_expenses(
        db, principal, start=start, end=end, store_id=store_id, category=category, supplier_id=supplier_id
    )


@router.get("/suppliers", response_model=list[ExpenseSupplier])
def suppliers(db: Db, _: CanManage, q: Annotated[str | None, Query(max_length=80)] = None) -> list[ExpenseSupplier]:
    return expense_service.search_suppliers(db, q)


@router.post("/suppliers", response_model=SupplierOut, status_code=201)
def create_supplier(payload: SupplierCreate, db: Db, principal: CanManage) -> SupplierOut:
    if not principal.permissions.intersection({"payables:manage", "portal:inventory_manage"}):
        raise ApiError(403, "forbidden", "You do not have permission for this action.")
    return import_batch_service.create_supplier(db, payload)


@router.get("/categories", response_model=list[ExpenseCategoryOut])
def categories(db: Db, _: CanManage, include_inactive: bool = False) -> list[ExpenseCategoryOut]:
    return expense_catalog.list_categories(db, active_only=not include_inactive)


@router.post("/categories", response_model=ExpenseCategoryOut, status_code=201)
def create_category(payload: ExpenseCategoryIn, db: Db, principal: CanManage) -> ExpenseCategoryOut:
    return expense_catalog.create_category(db, principal, payload.name, payload.description)


@router.post("/categories/{category_id}/deactivate", response_model=ExpenseCategoryOut)
def deactivate_category(category_id: uuid.UUID, db: Db, principal: CanManage) -> ExpenseCategoryOut:
    return expense_catalog.deactivate(db, principal, category_id)


@router.get("/{expense_id}/bill", response_model=ExpenseBillOut)
def bill(expense_id: uuid.UUID, db: Db, principal: CanManage) -> ExpenseBillOut:
    expense = expense_service.get_expense(db, principal, expense_id)
    return expense_bills.read_for(db, expense)


@router.post("", response_model=ExpenseOut, status_code=201)
def record(payload: ExpenseCreate, db: Db, principal: CanManage) -> ExpenseOut:
    return expense_service.record(db, principal, payload)


@router.post("/{expense_id}/void", response_model=ExpenseOut)
def void(expense_id: uuid.UUID, payload: ExpenseVoid, db: Db, principal: CanManage) -> ExpenseOut:
    return expense_service.void(db, principal, expense_id, payload.reason)


@router.get("/petty-cash/{store_id}", response_model=PettyCashOut)
def petty_cash(store_id: uuid.UUID, db: Db, principal: CanManage) -> PettyCashOut:
    return expense_service.petty_cash(db, principal, store_id)


@router.post("/petty-cash/top-up", response_model=PettyCashOut)
def top_up(payload: PettyCashTopUp, db: Db, principal: CanManage) -> PettyCashOut:
    return expense_service.top_up(db, principal, payload)


@router.post("/petty-cash/count", response_model=PettyCashOut)
def count(payload: PettyCashCount, db: Db, principal: CanManage) -> PettyCashOut:
    return expense_service.count(db, principal, payload)
