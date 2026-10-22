"""Food and beverage stock.

Prepared dishes are not a quantity on a shelf. Selling one draws its recipe from raw ingredients and
packaged goods, and the menu view reports how many portions that stock can still make.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.recipe import Recipe
from app.services import recipe_service


@dataclass(frozen=True)
class PortionAvailability:
    portions: int
    limiting: tuple[str, ...]
    menu_status: str


def consume_sale(
    db: Session, *, sale_id: uuid.UUID, store_id: uuid.UUID, user_id: uuid.UUID, dishes: list[recipe_service.SoldDish]
) -> None:
    """Draws recipe ingredients for the made-to-order lines on a completed sale."""
    recipe_service.consume(db, sale_id=sale_id, store_id=store_id, user_id=user_id, dishes=dishes)


def _at_store(recipe: Recipe, available: dict[uuid.UUID, int], names: dict[uuid.UUID, str]) -> tuple[int, list[str]]:
    scored: list[tuple[int, str]] = []
    for line in recipe.lines:
        have = available.get(line.ingredient_id, 0)
        can = (have * recipe.yield_quantity) // line.quantity if line.quantity else 0
        scored.append((can, names.get(line.ingredient_id, "Ingredient")))
    if not scored:
        return 0, []
    best = min(can for can, _name in scored)
    return best, [name for can, name in scored if can == best]


def menu_portions(
    db: Session, product_ids: list[uuid.UUID], store_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PortionAvailability]:
    """Max portions of each dish the listed branches can still prepare from ingredient stock."""
    if not product_ids:
        return {}
    recipes = {
        recipe.product_id: recipe
        for recipe in db.scalars(select(Recipe).where(Recipe.product_id.in_(product_ids))).all()
    }
    if not recipes:
        return {}
    ingredient_ids = {line.ingredient_id for recipe in recipes.values() for line in recipe.lines}
    names = {
        product.id: product.name
        for product in db.scalars(select(Product).where(Product.id.in_(ingredient_ids))).all()
    }
    by_store: dict[uuid.UUID, dict[uuid.UUID, int]] = defaultdict(dict)
    if ingredient_ids and store_ids:
        levels = db.scalars(
            select(InventoryLevel).where(
                InventoryLevel.product_id.in_(ingredient_ids),
                InventoryLevel.store_id.in_(store_ids),
            )
        ).all()
        for level in levels:
            by_store[level.store_id][level.product_id] = max(0, level.quantity_on_hand - level.quantity_reserved)
    found: dict[uuid.UUID, PortionAvailability] = {}
    branches = store_ids or [uuid.UUID(int=0)]
    for product_id, recipe in recipes.items():
        portions = 0
        limiting: list[str] = []
        for store_id in branches:
            can, names_limit = _at_store(recipe, by_store.get(store_id, {}), names)
            portions += can
            if not limiting:
                limiting = names_limit
        found[product_id] = PortionAvailability(
            portions=portions,
            limiting=tuple(limiting),
            menu_status="unavailable" if portions <= 0 else "available",
        )
    return found
