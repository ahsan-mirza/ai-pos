import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.cheques import ChequeAction, ChequeList, ChequeOut, ChequeStatus
from app.services import cheque_service

router = APIRouter()
CanManage = Annotated[Principal, Depends(authorize(Permission.CHEQUES_MANAGE))]


@router.get("", response_model=ChequeList)
def list_cheques(
    db: Annotated[Session, Depends(get_db)],
    principal: CanManage,
    status: ChequeStatus | None = None,
    customer_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> ChequeList:
    return cheque_service.list_cheques(
        db, status=status, customer_id=customer_id, store_scope=principal.store_id, limit=limit
    )


@router.post("/{cheque_id}/{action}", response_model=ChequeOut)
def cheque_action(
    cheque_id: uuid.UUID,
    action: Literal["deposit", "clear", "bounce", "cancel"],
    payload: ChequeAction,
    db: Annotated[Session, Depends(get_db)],
    principal: CanManage,
) -> ChequeOut:
    user_id = principal.user.id if principal.user is not None else None
    return cheque_service.act(db, cheque_id, action, payload, user_id, principal.store_id)
