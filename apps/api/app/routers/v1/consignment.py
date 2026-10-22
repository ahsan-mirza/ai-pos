import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.consignment import ConsignmentOverview, SettlementCreate, SettlementOut
from app.services import consignment_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PAYABLES_MANAGE))]


@router.get("", response_model=ConsignmentOverview)
def overview(db: Db, _: CanManage) -> ConsignmentOverview:
    """Supplier-owned stock per supplier: on hand, sold, and what is owed but not yet settled."""
    return consignment_service.overview(db)


@router.get("/settlements", response_model=list[SettlementOut])
def settlements(
    db: Db,
    _: CanManage,
    supplier_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[SettlementOut]:
    return consignment_service.settlements(db, supplier_id, limit)


@router.post("/settlements", response_model=list[SettlementOut], status_code=201)
def settle(payload: SettlementCreate, db: Db, principal: CanManage) -> list[SettlementOut]:
    """Bills the supplier for units sold since the last settlement (one bill per branch)."""
    user_id = principal.user.id if principal.user is not None else None
    return consignment_service.settle(db, payload, user_id)
