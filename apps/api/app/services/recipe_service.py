"""Recipes and ingredients. A dish with a recipe carries no stock: selling it draws each ingredient (RECIPE_OUT),
scaled by the quantity sold over the recipe's yield and adjusted by the modifiers chosen, and its cost is what those
ingredients cost. A sale is never refused for missing ingredients; the shortfall is recorded for the usage report."""

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.capabilities import Capability, has_capability
from app.core.errors import ApiError
from app.models.batch import BatchAllocation
from app.models.inventory import InventoryLevel, StockMovement
from app.models.menu import ModifierOption
from app.models.product import Product
from app.models.recipe import ModifierIngredient, Recipe, RecipeLine, RecipeUsage
from app.models.sale_item import SaleItem
from app.schemas.recipes import (
    ModifierIngredientOut,
    ModifierRecipeIn,
    ModifierRecipeOut,
    RecipeIn,
    RecipeLineOut,
    RecipeOut,
    UsageVarianceReport,
    UsageVarianceRow,
)
from app.services import audit, costing, weighed
from app.services.inventory import move_stock
from app.services.settings_service import cached_settings

ADJUSTMENT_MOVEMENTS = ("AUDIT_ADJUSTMENT", "DAMAGE_SHRINKAGE")


def recipes_enabled(db: Session) -> bool:
    return has_capability(db, Capability.RECIPES)


def recipe_product_ids(db: Session, product_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not product_ids:
        return set()
    return set(db.scalars(select(Recipe.product_id).where(Recipe.product_id.in_(product_ids))).all())


# --- Editing ----------------------------------------------------------------------------------------------


def _price_before_vat(db: Session, product: Product) -> int:
    snapshot = cached_settings(db)
    if not snapshot.prices_include_vat or product.tax_category != "STANDARD" or snapshot.standard_rate_bps <= 0:
        return product.price_cents
    return (product.price_cents * 10_000 + (10_000 + snapshot.standard_rate_bps) // 2) // (
        10_000 + snapshot.standard_rate_bps
    )


def _unit_costs(db: Session, ingredient_ids: set[uuid.UUID]) -> dict[uuid.UUID, int | None]:
    return {ingredient_id: costing.fallback_unit_cost(db, ingredient_id) for ingredient_id in ingredient_ids}


def recipe_out(db: Session, product: Product, recipe: Recipe) -> RecipeOut:
    ingredients = {
        item.id: item
        for item in db.scalars(select(Product).where(Product.id.in_({line.ingredient_id for line in recipe.lines})))
    }
    costs = _unit_costs(db, set(ingredients))
    lines: list[RecipeLineOut] = []
    batch = 0
    estimated = False
    for line in recipe.lines:
        ingredient = ingredients.get(line.ingredient_id)
        unit = costs.get(line.ingredient_id)
        cost = weighed.amount(line.quantity, unit or 0, weighed.scale_of(ingredient))
        estimated = estimated or unit is None
        batch += cost
        lines.append(
            RecipeLineOut(
                ingredient_id=line.ingredient_id,
                ingredient_name=ingredient.name if ingredient else "Removed product",
                sku=ingredient.sku if ingredient else "",
                sold_by_weight=bool(ingredient and ingredient.sold_by_weight),
                quantity=line.quantity,
                unit_cost_cents=unit,
                cost_cents=cost,
                cost_estimated=unit is None,
            )
        )
    # One dish unit: a portion, or a kilogram for a dish sold by weight (its price is per kilogram).
    per = weighed.GRAMS_PER_KG if product.sold_by_weight else 1
    unit_cost = weighed.amount(per, batch, recipe.yield_quantity)
    net = _price_before_vat(db, product)
    return RecipeOut(
        product_id=product.id,
        product_name=product.name,
        price_cents=product.price_cents,
        sold_by_weight=product.sold_by_weight,
        yield_quantity=recipe.yield_quantity,
        notes=recipe.notes,
        lines=lines,
        batch_cost_cents=batch,
        unit_cost_cents=unit_cost,
        margin_bps=((net - unit_cost) * 10_000 // net) if net > 0 else None,
        cost_estimated=estimated,
        updated_at=recipe.updated_at,
    )


def _product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product was not found.")
    return product


def list_recipes(db: Session) -> list[RecipeOut]:
    recipes = db.scalars(select(Recipe)).all()
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([recipe.product_id for recipe in recipes])))
    }
    rows = [recipe_out(db, products[recipe.product_id], recipe) for recipe in recipes if recipe.product_id in products]
    return sorted(rows, key=lambda row: row.product_name.lower())


def get_recipe(db: Session, product_id: uuid.UUID) -> RecipeOut:
    product = _product(db, product_id)
    recipe = db.scalar(select(Recipe).where(Recipe.product_id == product_id))
    if recipe is None:
        raise ApiError(404, "not_found", "This product has no recipe yet.")
    return recipe_out(db, product, recipe)


def _check_ingredients(db: Session, product: Product, ids: list[uuid.UUID]) -> None:
    if len(set(ids)) != len(ids):
        raise ApiError(422, "invalid_request", "List each ingredient once.")
    if product.id in ids:
        raise ApiError(422, "invalid_request", "A dish cannot be its own ingredient.")
    found = {item.id: item for item in db.scalars(select(Product).where(Product.id.in_(ids)))}
    for ingredient_id in ids:
        ingredient = found.get(ingredient_id)
        if ingredient is None:
            raise ApiError(422, "invalid_request", "An ingredient was not found.")
        if ingredient.is_serialized or ingredient.is_service or ingredient.is_open_price:
            raise ApiError(
                422, "invalid_request", f"{ingredient.name} is not a stocked item and cannot be an ingredient."
            )
    nested = recipe_product_ids(db, set(ids))
    if nested:
        names = ", ".join(found[item].name for item in nested)
        raise ApiError(422, "invalid_request", f"{names} has its own recipe; list its ingredients instead.")


def preview_recipe(db: Session, product_id: uuid.UUID, data: RecipeIn) -> RecipeOut:
    """Costs a draft without saving it, so the editor shows the dish cost and margin as lines change."""
    product = _product(db, product_id)
    _check_ingredients(db, product, [line.ingredient_id for line in data.lines])
    draft = Recipe(product_id=product_id, yield_quantity=data.yield_quantity, notes=data.notes)
    draft.lines = [
        RecipeLine(ingredient_id=line.ingredient_id, quantity=line.quantity, position=index)
        for index, line in enumerate(data.lines)
    ]
    return recipe_out(db, product, draft)


def save_recipe(db: Session, product_id: uuid.UUID, data: RecipeIn, user_id: uuid.UUID | None) -> RecipeOut:
    from app.models.menu import ComboSlot
    from app.services.item_type import apply_item_type

    product = _product(db, product_id)
    if product.is_ingredient:
        raise ApiError(422, "invalid_request", f"{product.name} is an ingredient; dishes have recipes.")
    if product.is_serialized or product.is_open_price:
        raise ApiError(422, "invalid_request", f"{product.name} cannot have a recipe.")
    if db.scalar(select(ComboSlot.id).where(ComboSlot.product_id == product_id).limit(1)):
        raise ApiError(422, "invalid_request", f"{product.name} is a meal. Give its dishes recipes instead.")
    apply_item_type(db, product, "MADE_TO_ORDER")
    if db.scalar(select(Recipe.id).join(RecipeLine).where(RecipeLine.ingredient_id == product_id).limit(1)):
        raise ApiError(422, "invalid_request", f"{product.name} is an ingredient of another dish.")
    _check_ingredients(db, product, [line.ingredient_id for line in data.lines])
    recipe = db.scalar(select(Recipe).where(Recipe.product_id == product_id))
    before = None
    if recipe is None:
        recipe = Recipe(product_id=product_id)
        db.add(recipe)
    else:
        before = {"yield": recipe.yield_quantity, "lines": [[str(x.ingredient_id), x.quantity] for x in recipe.lines]}
        recipe.lines.clear()
        db.flush()
    recipe.yield_quantity = data.yield_quantity
    recipe.notes = (data.notes or "").strip() or None
    for position, line in enumerate(data.lines):
        recipe.lines.append(RecipeLine(ingredient_id=line.ingredient_id, quantity=line.quantity, position=position))
    audit.record(
        db,
        action_type="UPDATE" if before else "CREATE",
        action="recipe.save",
        target_entity="Product",
        target_entity_id=product_id,
        user_id=user_id,
        old_values=before,
        new_values={"yield": data.yield_quantity, "lines": [[str(x.ingredient_id), x.quantity] for x in data.lines]},
    )
    db.commit()
    db.refresh(recipe)
    return recipe_out(db, product, recipe)


def delete_recipe(db: Session, product_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    recipe = db.scalar(select(Recipe).where(Recipe.product_id == product_id))
    if recipe is None:
        raise ApiError(404, "not_found", "This product has no recipe.")
    db.delete(recipe)
    audit.record(
        db,
        action_type="DELETE",
        action="recipe.delete",
        target_entity="Product",
        target_entity_id=product_id,
        user_id=user_id,
    )
    db.commit()


def _modifier_out(db: Session, option_id: uuid.UUID) -> ModifierRecipeOut:
    rows = db.scalars(select(ModifierIngredient).where(ModifierIngredient.option_id == option_id)).all()
    products = {
        item.id: item for item in db.scalars(select(Product).where(Product.id.in_({row.ingredient_id for row in rows})))
    }
    return ModifierRecipeOut(
        option_id=option_id,
        lines=[
            ModifierIngredientOut(
                ingredient_id=row.ingredient_id,
                quantity=row.quantity,
                ingredient_name=products[row.ingredient_id].name if row.ingredient_id in products else "Removed",
                sold_by_weight=bool(row.ingredient_id in products and products[row.ingredient_id].sold_by_weight),
            )
            for row in rows
        ],
    )


def get_modifier_recipe(db: Session, option_id: uuid.UUID) -> ModifierRecipeOut:
    if db.get(ModifierOption, option_id) is None:
        raise ApiError(404, "not_found", "Modifier option was not found.")
    return _modifier_out(db, option_id)


def save_modifier_recipe(db: Session, option_id: uuid.UUID, data: ModifierRecipeIn) -> ModifierRecipeOut:
    if db.get(ModifierOption, option_id) is None:
        raise ApiError(404, "not_found", "Modifier option was not found.")
    ids = [line.ingredient_id for line in data.lines]
    if len(set(ids)) != len(ids) or any(line.quantity == 0 for line in data.lines):
        raise ApiError(422, "invalid_request", "List each ingredient once, with a non-zero quantity.")
    found = set(db.scalars(select(Product.id).where(Product.id.in_(ids))).all())
    if found != set(ids):
        raise ApiError(422, "invalid_request", "An ingredient was not found.")
    for row in db.scalars(select(ModifierIngredient).where(ModifierIngredient.option_id == option_id)).all():
        db.delete(row)
    db.flush()
    for line in data.lines:
        db.add(ModifierIngredient(option_id=option_id, ingredient_id=line.ingredient_id, quantity=line.quantity))
    db.commit()
    return _modifier_out(db, option_id)


# --- Selling ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SoldDish:
    sale_item_id: uuid.UUID
    product: Product
    quantity: int
    modifiers: list[dict] | None


def _needs(db: Session, dishes: list[SoldDish]) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
    """Ingredient quantities each sold line calls for: recipe lines x quantity / yield, plus modifier deltas."""
    recipes = {
        recipe.product_id: recipe
        for recipe in db.scalars(select(Recipe).where(Recipe.product_id.in_({dish.product.id for dish in dishes})))
    }
    option_ids = {
        uuid.UUID(str(choice["option_id"]))
        for dish in dishes
        for choice in dish.modifiers or []
        if isinstance(choice, dict) and choice.get("option_id")
    }
    deltas: dict[uuid.UUID, list[ModifierIngredient]] = defaultdict(list)
    if option_ids:
        for row in db.scalars(select(ModifierIngredient).where(ModifierIngredient.option_id.in_(option_ids))):
            deltas[row.option_id].append(row)
    needs: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
    for dish in dishes:
        recipe = recipes.get(dish.product.id)
        if recipe is None:
            continue
        wanted: dict[uuid.UUID, int] = defaultdict(int)
        for line in recipe.lines:
            wanted[line.ingredient_id] += weighed.amount(dish.quantity, line.quantity, recipe.yield_quantity)
        # Modifiers apply per item; a dish sold by weight is one item whatever it weighs.
        items = 1 if dish.product.sold_by_weight else dish.quantity
        for choice in dish.modifiers or []:
            option = choice.get("option_id") if isinstance(choice, dict) else None
            for row in deltas.get(uuid.UUID(str(option)), []) if option else []:
                wanted[row.ingredient_id] += row.quantity * items
        # A meal line sells several dishes; their ingredients add up on that one line.
        line = needs.setdefault(dish.sale_item_id, {})
        for key, value in wanted.items():
            if value > 0:
                line[key] = line.get(key, 0) + value
    return {key: value for key, value in needs.items() if value}


def _drawn_unit_cost(db: Session, movement_id: uuid.UUID) -> int | None:
    quantity, total = db.execute(
        select(
            func.sum(BatchAllocation.quantity),
            func.sum(BatchAllocation.quantity * BatchAllocation.unit_cost_cents),
        ).where(BatchAllocation.stock_movement_id == movement_id)
    ).one()
    if not quantity:
        return None
    return (int(total) + int(quantity) // 2) // int(quantity)


def consume(
    db: Session, *, sale_id: uuid.UUID, store_id: uuid.UUID, user_id: uuid.UUID, dishes: list[SoldDish]
) -> None:
    """Draws the ingredients for the dishes on a recorded sale and writes each dish line's cost."""
    needs = _needs(db, dishes)
    if not needs:
        return
    totals: dict[uuid.UUID, int] = defaultdict(int)
    for wanted in needs.values():
        for ingredient_id, quantity in wanted.items():
            totals[ingredient_id] += quantity
    ingredients = {item.id: item for item in db.scalars(select(Product).where(Product.id.in_(set(totals))))}
    unit_costs: dict[uuid.UUID, int | None] = {}
    drawn: dict[uuid.UUID, int] = {}
    shortfalls: dict[str, int] = {}
    for ingredient_id, quantity in totals.items():
        level = db.scalar(
            select(InventoryLevel)
            .where(InventoryLevel.product_id == ingredient_id, InventoryLevel.store_id == store_id)
            .with_for_update()
        )
        available = max(0, level.quantity_on_hand - level.quantity_reserved) if level is not None else 0
        take = min(quantity, available)
        unit: int | None = None
        if take > 0:
            level = move_stock(
                db,
                product_id=ingredient_id,
                store_id=store_id,
                quantity=-take,
                movement_type="RECIPE_OUT",
                reference_type="sale_recipe",
                reference_id=sale_id,
                user_id=user_id,
            )
            before = level.quantity_on_hand + take
            if level.min_reorder_level > 0 and level.quantity_on_hand <= level.min_reorder_level < before:
                ingredient = ingredients.get(ingredient_id)
                audit.record(
                    db,
                    action_type="UPDATE",
                    action="inventory.reorder_alert",
                    target_entity="Product",
                    target_entity_id=ingredient_id,
                    store_id=store_id,
                    user_id=user_id,
                    client_device="system",
                    details={
                        "name": ingredient.name if ingredient else "",
                        "on_hand": level.quantity_on_hand,
                        "min_reorder_level": level.min_reorder_level,
                        "sale_id": str(sale_id),
                    },
                )
            movement = db.scalar(
                select(StockMovement.id)
                .where(
                    StockMovement.reference_id == sale_id,
                    StockMovement.product_id == ingredient_id,
                    StockMovement.movement_type == "RECIPE_OUT",
                )
                .order_by(StockMovement.created_at.desc())
                .limit(1)
            )
            unit = _drawn_unit_cost(db, movement) if movement is not None else None
        unit_costs[ingredient_id] = unit if unit is not None else costing.fallback_unit_cost(db, ingredient_id)
        drawn[ingredient_id] = take
        if take < quantity:
            shortfalls[str(ingredient_id)] = quantity - take

    for ingredient_id, quantity in totals.items():
        ingredient = ingredients.get(ingredient_id)
        db.add(
            RecipeUsage(
                sale_id=sale_id,
                store_id=store_id,
                ingredient_id=ingredient_id,
                quantity_needed=quantity,
                quantity_drawn=drawn[ingredient_id],
                cost_cents=weighed.amount(quantity, unit_costs[ingredient_id] or 0, weighed.scale_of(ingredient)),
            )
        )
    items = {item.id: item for item in db.scalars(select(SaleItem).where(SaleItem.id.in_(list(needs))))}
    for sale_item_id, wanted in needs.items():
        item = items.get(sale_item_id)
        if item is None:
            continue
        item.cost_cents = sum(
            weighed.amount(quantity, unit_costs[ingredient_id] or 0, weighed.scale_of(ingredients.get(ingredient_id)))
            for ingredient_id, quantity in wanted.items()
        )
        item.cost_estimated = any(unit_costs[ingredient_id] is None for ingredient_id in wanted)
    if shortfalls:
        audit.record(
            db,
            action_type="UPDATE",
            action="recipe.stock_short",
            target_entity="Sale",
            target_entity_id=sale_id,
            store_id=store_id,
            client_device="system",
            details={"short": shortfalls},
        )
    db.flush()


# --- Usage report -----------------------------------------------------------------------------------------


def usage_variance(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> UsageVarianceReport:
    """Theoretical usage (what the recipes of the dishes sold call for) against actual usage: what was drawn, less
    what stock counts and waste write-offs corrected. Positive variance means more was used than the recipes say."""
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Pick a period of at most 400 days that ends after it starts.")
    since = datetime.combine(start, time.min, UTC)
    until = datetime.combine(end + timedelta(days=1), time.min, UTC)
    usage = select(
        RecipeUsage.ingredient_id,
        func.sum(RecipeUsage.quantity_needed),
        func.sum(RecipeUsage.quantity_drawn),
        func.sum(RecipeUsage.cost_cents),
    ).where(RecipeUsage.created_at >= since, RecipeUsage.created_at < until)
    if store_id is not None:
        usage = usage.where(RecipeUsage.store_id == store_id)
    used = {
        row[0]: (int(row[1]), int(row[2]), int(row[3])) for row in db.execute(usage.group_by(RecipeUsage.ingredient_id))
    }
    if not used:
        return UsageVarianceReport(start=start, end=end, store_id=store_id, rows=[])
    adjusted = select(StockMovement.product_id, func.sum(StockMovement.quantity)).where(
        StockMovement.product_id.in_(list(used)),
        StockMovement.movement_type.in_(ADJUSTMENT_MOVEMENTS),
        StockMovement.reference_type != "opening_balance",
        StockMovement.created_at >= since,
        StockMovement.created_at < until,
    )
    if store_id is not None:
        adjusted = adjusted.where(StockMovement.store_id == store_id)
    adjustments = {row[0]: int(row[1]) for row in db.execute(adjusted.group_by(StockMovement.product_id))}
    products = {item.id: item for item in db.scalars(select(Product).where(Product.id.in_(list(used))))}
    rows: list[UsageVarianceRow] = []
    for ingredient_id, (theoretical, drawn, cost) in used.items():
        product = products.get(ingredient_id)
        adjustment = adjustments.get(ingredient_id, 0)
        actual = drawn - adjustment
        variance = actual - theoretical
        rows.append(
            UsageVarianceRow(
                ingredient_id=ingredient_id,
                name=product.name if product else "Removed product",
                sku=product.sku if product else "",
                sold_by_weight=bool(product and product.sold_by_weight),
                theoretical=theoretical,
                drawn=drawn,
                adjustments=adjustment,
                actual=actual,
                variance=variance,
                # At the average cost the recipes were drawn at.
                variance_cost_cents=round(variance * cost / theoretical) if theoretical else 0,
            )
        )
    rows.sort(key=lambda row: abs(row.variance_cost_cents), reverse=True)
    return UsageVarianceReport(start=start, end=end, store_id=store_id, rows=rows)
