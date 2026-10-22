import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.auth import PasswordReset, PinReset, RegisterStaffOut, UserCreate, UserOut, UserUpdate
from app.services import rbac_service

router = APIRouter()

AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanRead = Annotated[Principal, Depends(authorize(Permission.USERS_READ))]
CanCreate = Annotated[Principal, Depends(authorize(Permission.USERS_CREATE))]
CanUpdate = Annotated[Principal, Depends(authorize(Permission.USERS_UPDATE))]
CanDelete = Annotated[Principal, Depends(authorize(Permission.USERS_DELETE))]
Db = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[UserOut])
def list_users(db: Db, actor: CanRead) -> list[UserOut]:
    return rbac_service.list_users(db, actor)


@router.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: CanCreate,
) -> UserOut:
    return rbac_service.create_user(db, settings, actor, payload)


@router.get("/register-staff", response_model=list[RegisterStaffOut])
def register_staff(db: Db, principal: AtRegister, store_id: uuid.UUID | None = None) -> list[RegisterStaffOut]:
    """Who can be picked as "Served by" at a till: active staff with POS access at the branch."""
    branch = principal.store_id or store_id
    rows = db.scalars(select(User).where(User.is_active.is_(True), User.has_pos_access.is_(True))).unique().all()
    return [
        RegisterStaffOut(id=user.id, full_name=user.full_name, role_name=user.role.name if user.role else "")
        for user in sorted(rows, key=lambda row: row.full_name.lower())
        if Permission.POS_ACCESS.value in user.permissions and (user.store_id is None or user.store_id == branch)
    ]


@router.get("/{user_id}", response_model=UserOut)
def get_user(user_id: uuid.UUID, db: Db, actor: CanRead) -> UserOut:
    return rbac_service.user_out(rbac_service.get_user(db, actor, user_id))


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: uuid.UUID, payload: UserUpdate, db: Db, actor: CanUpdate) -> UserOut:
    return rbac_service.update_user(db, actor, user_id, payload)


@router.post("/{user_id}/password", response_model=UserOut)
def reset_password(user_id: uuid.UUID, payload: PasswordReset, db: Db, actor: CanUpdate) -> UserOut:
    return rbac_service.set_password(db, actor, user_id, payload.password)


@router.post("/{user_id}/pin", response_model=UserOut)
def reset_pin(
    user_id: uuid.UUID,
    payload: PinReset,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: CanUpdate,
) -> UserOut:
    return rbac_service.set_pin(db, settings, actor, user_id, payload.pin)


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: uuid.UUID, db: Db, actor: CanDelete) -> Response:
    rbac_service.delete_user(db, actor, user_id)
    return Response(status_code=204)
