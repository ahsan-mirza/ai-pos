import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.schemas.inventory import CategoryOut, CategoryUpdate, CategoryWrite
from app.services import category_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[
    Principal,
    Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos"))),
]


def require_catalog_admin(
    principal: Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))],
) -> Principal:
    """Categories are shared by every branch, so only users not bound to one store may change them."""
    if principal.store_id is not None:
        raise ApiError(403, "store_scope", "Categories are shared across branches. Ask a Super Admin to change them.")
    return principal


CanManage = Annotated[Principal, Depends(require_catalog_admin)]


@router.get("", response_model=list[CategoryOut])
def list_categories(db: Db, _: CanRead) -> list[CategoryOut]:
    return category_service.list_categories(db)


@router.post("", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryWrite, db: Db, _: CanManage) -> CategoryOut:
    return category_service.create_category(db, payload)


@router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: uuid.UUID, payload: CategoryUpdate, db: Db, _: CanManage) -> CategoryOut:
    return category_service.update_category(db, category_id, payload)


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: uuid.UUID, db: Db, _: CanManage) -> Response:
    category_service.delete_category(db, category_id)
    return Response(status_code=204)


@router.post("/{category_id}/sub-categories", response_model=CategoryOut, status_code=201)
def create_sub_category(category_id: uuid.UUID, payload: CategoryWrite, db: Db, _: CanManage) -> CategoryOut:
    return category_service.create_sub_category(db, category_id, payload)


@router.patch("/sub-categories/{sub_category_id}", response_model=CategoryOut)
def update_sub_category(sub_category_id: uuid.UUID, payload: CategoryUpdate, db: Db, _: CanManage) -> CategoryOut:
    return category_service.update_sub_category(db, sub_category_id, payload)


@router.delete("/sub-categories/{sub_category_id}", response_model=CategoryOut)
def delete_sub_category(sub_category_id: uuid.UUID, db: Db, _: CanManage) -> CategoryOut:
    return category_service.delete_sub_category(db, sub_category_id)
