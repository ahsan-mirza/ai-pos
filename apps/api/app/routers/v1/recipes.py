import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import Principal, authorize
from app.core.permissions import Permission
from app.schemas.recipes import ModifierRecipeIn, ModifierRecipeOut, RecipeIn, RecipeOut, UsageVarianceReport
from app.services import recipe_service

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
CanManage = Annotated[Principal, Depends(authorize(Permission.PORTAL_INVENTORY_MANAGE))]
CanReport = Annotated[Principal, Depends(authorize(Permission.PORTAL_REPORTS_READ))]


def _user_id(principal: Principal) -> uuid.UUID | None:
    return principal.user.id if principal.user is not None else None


@router.get("", response_model=list[RecipeOut])
def list_recipes(db: Db, principal: CanManage) -> list[RecipeOut]:
    return recipe_service.list_recipes(db)


@router.get("/variance", response_model=UsageVarianceReport)
def variance(
    db: Db,
    principal: CanReport,
    start: Annotated[date, Query(alias="from")],
    end: Annotated[date, Query(alias="to")],
    store_id: uuid.UUID | None = None,
) -> UsageVarianceReport:
    scope = principal.store_id if principal.store_id is not None else store_id
    return recipe_service.usage_variance(db, start=start, end=end, store_id=scope)


@router.get("/modifier-options/{option_id}", response_model=ModifierRecipeOut)
def get_modifier_recipe(option_id: uuid.UUID, db: Db, principal: CanManage) -> ModifierRecipeOut:
    return recipe_service.get_modifier_recipe(db, option_id)


@router.put("/modifier-options/{option_id}", response_model=ModifierRecipeOut)
def save_modifier_recipe(
    option_id: uuid.UUID, payload: ModifierRecipeIn, db: Db, principal: CanManage
) -> ModifierRecipeOut:
    return recipe_service.save_modifier_recipe(db, option_id, payload)


@router.get("/{product_id}", response_model=RecipeOut)
def get_recipe(product_id: uuid.UUID, db: Db, principal: CanManage) -> RecipeOut:
    return recipe_service.get_recipe(db, product_id)


@router.post("/{product_id}/preview", response_model=RecipeOut)
def preview_recipe(product_id: uuid.UUID, payload: RecipeIn, db: Db, principal: CanManage) -> RecipeOut:
    return recipe_service.preview_recipe(db, product_id, payload)


@router.put("/{product_id}", response_model=RecipeOut)
def save_recipe(product_id: uuid.UUID, payload: RecipeIn, db: Db, principal: CanManage) -> RecipeOut:
    return recipe_service.save_recipe(db, product_id, payload, _user_id(principal))


@router.delete("/{product_id}", status_code=204)
def delete_recipe(product_id: uuid.UUID, db: Db, principal: CanManage) -> Response:
    recipe_service.delete_recipe(db, product_id, _user_id(principal))
    return Response(status_code=204)
