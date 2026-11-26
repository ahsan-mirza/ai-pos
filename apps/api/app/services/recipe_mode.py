"""Product-level recipe requirement for restaurant and cafe menu items.

New order lines follow ``products.sell_without_recipe``. A cashier cannot
choose a different mode at the till. Other business types keep the existing
per-line permission. Historical lines are not rewritten.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.recipe import Recipe

RECIPE_REQUIRED = "A recipe is required for this product. Add its raw ingredients before saving."
INGREDIENT_LOCKED = "The ingredient requirement is set on the menu item. The till cannot change it."
SKIP_PERMISSION = "Skipping recipe ingredients needs permission."
MENU_PROFILES = frozenset({"restaurant", "cafe"})


def menu_profile(db: Session) -> bool:
    from app.services.settings_service import load_settings

    return load_settings(db).business_profile in MENU_PROFILES


def apply_sell_without_recipe(db: Session, product, requested: bool | None, *, sent: bool) -> None:
    """Store the toggle only for an active restaurant or cafe made-to-order item."""
    if not menu_profile(db) or product.item_type != "MADE_TO_ORDER":
        product.sell_without_recipe = False
        return
    if sent:
        product.sell_without_recipe = bool(requested)


def has_recipe(db: Session, product_id: uuid.UUID) -> bool:
    return db.scalar(select(Recipe.id).where(Recipe.product_id == product_id).limit(1)) is not None


def enforce_recipe_requirement(db: Session, product, *, creating: bool, fields: set[str]) -> None:
    """Active recipe-managed dishes need a recipe when that state is being set.

    A later edit that does not touch the toggle, item type, or active flag leaves
    an existing recipe-less dish alone. An empty recipe is not treated as prepared.
    """
    if not menu_profile(db) or product.item_type != "MADE_TO_ORDER":
        return
    if product.sell_without_recipe or product.is_active is False:
        return
    if not creating and not ({"sell_without_recipe", "is_active", "item_type"} & fields):
        return
    if not has_recipe(db, product.id):
        raise ApiError(422, "recipe_required", RECIPE_REQUIRED)


def ingredient_mode_error(db: Session, product, requested: bool, permissions: set[str]) -> str | None:
    """Return a refusal message, or None when the line matches the saved mode."""
    if menu_profile(db) and product.item_type == "MADE_TO_ORDER":
        if bool(requested) != bool(product.sell_without_recipe):
            return INGREDIENT_LOCKED
        return None
    if requested and Permission.POS_SKIP_RECIPE.value not in permissions:
        return SKIP_PERMISSION
    return None


def resolve_order_skip(db: Session, product, requested: bool | None, permissions: set[str]) -> tuple[bool, str | None]:
    """The skip flag to store, and a refusal when the till tried to override the menu item.

    A register that leaves the flag off follows the item. Sending the opposite of the item is refused.
    """
    if menu_profile(db) and product.item_type == "MADE_TO_ORDER":
        expected = bool(product.sell_without_recipe)
        if requested is None or bool(requested) == expected:
            return expected, None
        return expected, INGREDIENT_LOCKED
    if requested and Permission.POS_SKIP_RECIPE.value not in permissions:
        return False, SKIP_PERMISSION
    return bool(requested), None
