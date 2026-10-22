import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.warranty import PlanOut, PlanWrite, PolicyOut, PolicyWrite, RegistrationList, RegistrationOut
from app.services import warranty_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Config = Annotated[Settings, Depends(get_settings)]
CanRead = Annotated[
    Principal, Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos")))
]
CanManage = Annotated[Principal, Depends(authorize(Permission.WARRANTY_MANAGE))]


@router.get("", response_model=RegistrationList)
def registrations(
    db: Db,
    settings: Config,
    principal: CanRead,
    q: str | None = None,
    expiring_days: Annotated[int | None, Query(ge=1, le=365)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> RegistrationList:
    return warranty_service.list_registrations(
        db, settings, query=q, expiring_days=expiring_days, store_scope=principal.store_id, limit=limit
    )


@router.get("/lookup", response_model=RegistrationOut | None)
def lookup(db: Db, settings: Config, _: CanRead, serial: Annotated[str, Query(min_length=4, max_length=64)]):
    return warranty_service.lookup(db, settings, serial)


@router.get("/policies", response_model=list[PolicyOut])
def policies(db: Db, _: CanManage) -> list[PolicyOut]:
    return warranty_service.list_policies(db)


@router.post("/policies", response_model=list[PolicyOut], status_code=201)
def create_policy(payload: PolicyWrite, db: Db, _: CanManage) -> list[PolicyOut]:
    return warranty_service.save_policy(db, payload)


@router.put("/policies/{policy_id}", response_model=list[PolicyOut])
def update_policy(policy_id: uuid.UUID, payload: PolicyWrite, db: Db, _: CanManage) -> list[PolicyOut]:
    return warranty_service.save_policy(db, payload, policy_id)


@router.get("/plans", response_model=list[PlanOut])
def plans(db: Db, _: CanRead) -> list[PlanOut]:
    return warranty_service.list_plans(db)


@router.post("/plans", response_model=list[PlanOut], status_code=201)
def create_plan(payload: PlanWrite, db: Db, _: CanManage) -> list[PlanOut]:
    return warranty_service.create_plan(db, payload)
