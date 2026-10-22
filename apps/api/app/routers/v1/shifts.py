import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.shifts import ShiftOut
from app.services import shift_service

router = APIRouter()
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ, allow_device=True))]


@router.get("", response_model=list[ShiftOut])
def list_shifts(
    db: Annotated[Session, Depends(get_db)],
    principal: CanRead,
    store_id: uuid.UUID | None = None,
    status: Literal["OPEN", "CLOSED"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[ShiftOut]:
    scope = principal.store_id if principal.store_id is not None else store_id
    return shift_service.list_shifts(db, store_scope=scope, status=status, limit=limit)


@router.get("/{shift_id}", response_model=ShiftOut)
def get_shift(shift_id: uuid.UUID, db: Annotated[Session, Depends(get_db)], principal: CanRead) -> ShiftOut:
    return shift_service.get_shift(db, shift_id, principal.store_id)
