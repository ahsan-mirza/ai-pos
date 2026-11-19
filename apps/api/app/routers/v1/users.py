import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.user import User
from app.schemas.auth import PasswordReset, PinReset, RegisterStaffOut, UserCreate, UserOut, UserUpdate
from app.schemas.user_preference import CatalogueViewOut, CatalogueViewWrite
from app.services import rbac_service, user_preference_service

router = APIRouter()

AtRegister = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, allow_device=True, scopes=("pos", "portal")))
]
CanRead = Annotated[Principal, Depends(authorize(Permission.USERS_READ))]
CanCreate = Annotated[Principal, Depends(authorize(Permission.USERS_CREATE))]
CanUpdate = Annotated[Principal, Depends(authorize(Permission.USERS_UPDATE))]
CanDelete = Annotated[Principal, Depends(authorize(Permission.USERS_DELETE))]
OwnCatalogue = Annotated[
    Principal, Depends(authorize(Permission.POS_ACCESS, scopes=("pos", "portal")))
]
Db = Annotated[Session, Depends(get_db)]


def _signed_in(principal: Principal) -> User:
    if principal.user is None:
        raise ApiError(403, "forbidden", "This action requires a signed-in user.")
    return principal.user


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


@router.get("/me/preferences", response_model=CatalogueViewOut)
def read_my_catalogue_view(db: Db, actor: OwnCatalogue) -> CatalogueViewOut:
    """The signed-in cashier's catalogue view. A missing choice is grid."""
    return user_preference_service.read_catalogue_view(db, _signed_in(actor))


@router.put("/me/preferences/product-catalogue-view", response_model=CatalogueViewOut)
def save_my_catalogue_view(payload: CatalogueViewWrite, db: Db, actor: OwnCatalogue) -> CatalogueViewOut:
    """Save this cashier's view. The user id is the token subject, never a request field."""
    return user_preference_service.save_catalogue_view(
        db,
        _signed_in(actor),
        payload.product_catalogue_view,
        payload.updated_at,
    )


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
