import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.kitchen_agent import KitchenActionIn, KitchenActionOut, KitchenBrief
from app.services import kitchen_agent_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[Principal, Depends(authorize(Permission.PORTAL_ACCESS))]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


@router.get("", response_model=KitchenBrief)
def get_brief(
    db: Db,
    principal: CanRead,
    store_id: Annotated[uuid.UUID | None, Query()] = None,
) -> KitchenBrief:
    scope = principal.store_id if principal.store_id is not None else store_id
    return kitchen_agent_service.brief(db, scope)


@router.post("/actions", response_model=KitchenActionOut)
def act(
    data: KitchenActionIn,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    principal: CanManage,
) -> KitchenActionOut:
    return kitchen_agent_service.apply(db, settings, principal, data)
