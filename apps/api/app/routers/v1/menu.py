import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.menu import ComboIn, ComboOut, ModifierGroupIn, ModifierGroupOut, ProductGroupsIn, RegisterMenu
from app.services import combo_service, menu_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanRead = Annotated[
    Principal, Depends(authorize(Permission.PORTAL_ACCESS, allow_device=True, scopes=("portal", "pos")))
]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]


@router.get("/modifier-groups", response_model=list[ModifierGroupOut])
def list_groups(db: Db, _: CanRead) -> list[ModifierGroupOut]:
    return menu_service.list_groups(db)


@router.post("/modifier-groups", response_model=ModifierGroupOut, status_code=201)
def create_group(payload: ModifierGroupIn, db: Db, _: CanManage) -> ModifierGroupOut:
    return menu_service.create_group(db, payload)


@router.put("/modifier-groups/{group_id}", response_model=ModifierGroupOut)
def update_group(group_id: uuid.UUID, payload: ModifierGroupIn, db: Db, _: CanManage) -> ModifierGroupOut:
    return menu_service.update_group(db, group_id, payload)


@router.put("/products/{product_id}/modifier-groups", response_model=list[uuid.UUID])
def set_product_groups(product_id: uuid.UUID, payload: ProductGroupsIn, db: Db, _: CanManage) -> list[uuid.UUID]:
    return menu_service.set_product_groups(db, product_id, payload)


@router.get("/register", response_model=RegisterMenu)
def register_menu(db: Db, _: CanRead) -> RegisterMenu:
    return menu_service.register_menu(db)


@router.get("/combos", response_model=list[ComboOut])
def list_combos(db: Db, _: CanRead) -> list[ComboOut]:
    return combo_service.list_combos(db)


@router.post("/combos", response_model=ComboOut, status_code=201)
def create_combo(payload: ComboIn, db: Db, _: CanManage) -> ComboOut:
    return combo_service.create_combo(db, payload)


@router.get("/combos/{product_id}", response_model=ComboOut)
def get_combo(product_id: uuid.UUID, db: Db, _: CanRead) -> ComboOut:
    return combo_service.get_combo(db, product_id)


@router.put("/combos/{product_id}", response_model=ComboOut)
def update_combo(product_id: uuid.UUID, payload: ComboIn, db: Db, _: CanManage) -> ComboOut:
    return combo_service.update_combo(db, product_id, payload)


@router.delete("/combos/{product_id}", status_code=204)
def remove_combo(product_id: uuid.UUID, db: Db, _: CanManage) -> None:
    combo_service.remove_combo(db, product_id)
