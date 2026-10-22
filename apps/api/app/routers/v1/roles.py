import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.auth import PermissionGroupOut, RoleCreate, RoleOut, RoleUpdate
from app.services import rbac_service

router = APIRouter()

CanView = Annotated[Principal, Depends(authorize(Permission.USERS_READ))]
CanManage = Annotated[Principal, Depends(authorize(Permission.ROLES_MANAGE))]
Db = Annotated[Session, Depends(get_db)]


@router.get("/permissions", response_model=list[PermissionGroupOut])
def list_permissions(_: CanView) -> list[PermissionGroupOut]:
    return rbac_service.permission_catalog()


@router.get("", response_model=list[RoleOut])
def list_roles(db: Db, _: CanView) -> list[RoleOut]:
    return rbac_service.list_roles(db)


@router.post("", response_model=RoleOut, status_code=201)
def create_role(payload: RoleCreate, db: Db, actor: CanManage) -> RoleOut:
    return rbac_service.create_role(db, actor, payload)


@router.patch("/{role_id}", response_model=RoleOut)
def update_role(role_id: uuid.UUID, payload: RoleUpdate, db: Db, actor: CanManage) -> RoleOut:
    return rbac_service.update_role(db, actor, role_id, payload)


@router.delete("/{role_id}", status_code=204)
def delete_role(role_id: uuid.UUID, db: Db, actor: CanManage) -> Response:
    rbac_service.delete_role(db, actor, role_id)
    return Response(status_code=204)
