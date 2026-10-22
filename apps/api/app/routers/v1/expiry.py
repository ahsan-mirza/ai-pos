import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.expiry import ExpiringRow, ExpiryWriteOff, ExpiryWriteOffOut
from app.services import expiry_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanAdjust = Annotated[Principal, Depends(authorize(Permission.INVENTORY_ADJUST_STOCK))]


@router.get("/expiring", response_model=list[ExpiringRow])
def expiring(
    db: Db,
    principal: CanRead,
    store_id: uuid.UUID | None = None,
    days: Annotated[int | None, Query(ge=0, le=365)] = None,
) -> list[ExpiringRow]:
    return expiry_service.expiring(db, principal, store_id=store_id, days=days)


@router.post("/expiry-writeoff", response_model=ExpiryWriteOffOut)
def write_off(payload: ExpiryWriteOff, db: Db, principal: CanAdjust) -> ExpiryWriteOffOut:
    return expiry_service.write_off(db, principal, payload)
