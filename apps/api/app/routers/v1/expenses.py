import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.expenses import (
    ExpenseCategory,
    ExpenseCreate,
    ExpenseList,
    ExpenseOut,
    ExpenseVoid,
    PettyCashCount,
    PettyCashOut,
    PettyCashTopUp,
)
from app.services import expense_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.EXPENSES_MANAGE))]


@router.get("", response_model=ExpenseList)
def list_expenses(
    db: Db,
    principal: CanManage,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
    category: ExpenseCategory | None = None,
) -> ExpenseList:
    return expense_service.list_expenses(db, principal, start=start, end=end, store_id=store_id, category=category)


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
