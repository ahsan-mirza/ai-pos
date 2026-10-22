"""How a catalog item meets inventory.

MADE_TO_ORDER dishes (burgers, pasta, coffee) are prepared when sold and are omitted from on-hand counts.
RAW_INGREDIENT and PRE_PACKAGED items keep a real quantity, reorder level, and purchase trail.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.menu import ComboSlot
from app.models.product import Product
from app.models.recipe import Recipe

ITEM_TYPES = ("MADE_TO_ORDER", "RAW_INGREDIENT", "PRE_PACKAGED")

# Sample-menu drinks and snacks sold as units, not prepared from a recipe.
PACKAGED_SAMPLE_SKUS = frozenset(
    {
        "SAMPLE-SOFT-DRINK",
        "SAMPLE-WATER",
        "SAMPLE-CAFE-WATER",
        "SAMPLE-QSR-COLA",
        "SAMPLE-QSR-ORANGE-SODA",
        "SAMPLE-QSR-WATER",
        "SAMPLE-QSR-APPLE-JUICE",
    }
)


def _is_meal(db: Session, product: Product) -> bool:
    if product.id is None:
        return False
    return db.scalar(select(ComboSlot.id).where(ComboSlot.product_id == product.id).limit(1)) is not None


def apply_item_type(db: Session, product: Product, item_type: str) -> None:
    """Sets item_type and the stock flags that follow from it. Meals stay service items."""
    if item_type not in ITEM_TYPES:
        raise ApiError(422, "invalid_request", "Unknown item type.")
    if item_type != "PRE_PACKAGED" and product.is_serialized:
        raise ApiError(422, "invalid_request", "Serialized products are tracked packaged stock.")
    product.item_type = item_type
    if item_type == "MADE_TO_ORDER":
        product.is_stock_tracked = False
        product.is_ingredient = False
        if not _is_meal(db, product):
            product.is_service = False
        return
    if item_type == "RAW_INGREDIENT":
        if product.id is not None and db.scalar(select(Recipe.id).where(Recipe.product_id == product.id)):
            raise ApiError(422, "invalid_request", "A dish with a recipe cannot be an ingredient.")
        product.is_stock_tracked = True
        product.is_ingredient = True
        product.is_service = False
        return
    product.is_stock_tracked = True
    product.is_ingredient = False
