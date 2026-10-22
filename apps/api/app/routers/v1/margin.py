import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.margin import FloorOut, MarginExceptionList, MarginPolicyOut, MarginPolicyWrite
from app.services import margin_service
from app.services.tax import policy as tax_policy

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_PRICING_MANAGE))]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


@router.get("/floors", response_model=list[FloorOut])
def floors(db: Db, principal: AtRegister, store_id: uuid.UUID | None = None) -> list[FloorOut]:
    """Floor prices for the register's branch, cached by registers so they can warn offline."""
    scope = principal.store_id or store_id
    if scope is None:
        raise ApiError(422, "validation_error", "Pass the store_id.")
    return margin_service.floors(db, scope, tax_policy(db))


@router.get("/policies", response_model=list[MarginPolicyOut])
def policies(db: Db, _: CanRead) -> list[MarginPolicyOut]:
    return margin_service.list_policies(db)


@router.put("/policies", response_model=list[MarginPolicyOut])
def upsert_policy(payload: MarginPolicyWrite, db: Db, _: CanManage) -> list[MarginPolicyOut]:
    return margin_service.upsert_policy(db, payload)


@router.delete("/policies/{policy_id}", response_model=list[MarginPolicyOut])
def delete_policy(policy_id: uuid.UUID, db: Db, _: CanManage) -> list[MarginPolicyOut]:
    return margin_service.delete_policy(db, policy_id)


@router.get("/exceptions", response_model=MarginExceptionList)
def exceptions(
    db: Db,
    principal: CanRead,
    days: Annotated[int, Query(ge=1, le=365)] = 30,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> MarginExceptionList:
    return MarginExceptionList(
        total_shortfall_cents=margin_service.exception_total(db, principal.store_id, days),
        exceptions=margin_service.exceptions(db, store_scope=principal.store_id, days=days, limit=limit),
    )
