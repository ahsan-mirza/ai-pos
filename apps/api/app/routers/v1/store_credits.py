from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.store_credit import StoreCreditList, StoreCreditOut
from app.services import store_credit_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


@router.get("", response_model=StoreCreditList)
def list_credits(
    db: Db,
    principal: CanRead,
    open_only: bool = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> StoreCreditList:
    return store_credit_service.list_credits(db, open_only=open_only, store_scope=principal.store_id, limit=limit)


@router.get("/{code}", response_model=StoreCreditOut)
def lookup(code: str, db: Db, principal: AtRegister) -> StoreCreditOut:
    return store_credit_service.lookup(db, code)
