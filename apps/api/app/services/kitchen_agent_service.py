"""Kitchen brief for restaurant and cafe: what to order, use first, move, or take off the menu.

Numbers come from ingredient stock, recipes, and batch expiry. Nothing here is guessed by a language model,
and nothing is stored: the page and the morning job both call `brief`.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.purchasing import PurchaseOrder, PurchaseOrderLine
from app.models.recipe import Recipe
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.expiry import ExpiryWriteOff
from app.schemas.inventory import PurchaseOrderCreate, PurchaseOrderLineIn, TransferCreate, TransferLineIn
from app.schemas.kitchen_agent import KitchenActionIn, KitchenActionOut, KitchenBrief, KitchenCard
from app.services import expiry_service, fnb_service, inventory, margin_service, recipe_service
from app.services.channel_service import POSTED

LOOKBACK_DAYS = 28
HORIZON_DAYS = 3
WASTE_DAYS = 7
EXPIRY_DAYS = 7
WASTE_PERCENT = 15
CARD_CAP = 8

Kind = str


def brief(db: Session, store_id: uuid.UUID | None) -> KitchenBrief:
    """Cards for one branch, or every active branch when store_id is omitted."""
    stores = list(db.scalars(select(Store).where(Store.is_active.is_(True)).order_by(Store.code)))
    if store_id is not None:
        stores = [store for store in stores if store.id == store_id]
    cards: list[KitchenCard] = []
    for store in stores:
        cards.extend(_store_cards(db, store))
    return KitchenBrief(generated_at=datetime.now(UTC), store_id=store_id, cards=cards)


def apply(db: Session, settings: Settings, principal: Principal, data: KitchenActionIn) -> KitchenActionOut:
    """Turns one card into a draft document or an expiry write-off, using the existing stock services."""
    if data.action == "draft_purchase":
        return _draft_purchase(db, principal, data)
    if data.action == "draft_transfer":
        return _draft_transfer(db, settings, principal, data)
    return _write_off(db, principal, data)


def _store_cards(db: Session, store: Store) -> list[KitchenCard]:
    recipes = list(db.scalars(select(Recipe).options(selectinload(Recipe.lines))).all())
    if not recipes:
        return []
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_([recipe.product_id for recipe in recipes])))
    }
    ingredient_ids = {line.ingredient_id for recipe in recipes for line in recipe.lines}
    ingredients = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(ingredient_ids))).all()
    }
    on_hand = _on_hand(db, None)
    sold = _sold_portions(db, store.id)
    need = _ingredient_need(recipes, sold)
    raw_need = _ingredient_need_raw(recipes, sold)
    daily = {ingredient_id: quantity / LOOKBACK_DAYS for ingredient_id, quantity in raw_need.items()}
    reorder = _reorder(db, store.id)
    supplier = _suppliers(db, ingredient_ids)
    buckets: dict[Kind, list[KitchenCard]] = defaultdict(list)

    for ingredient_id in ingredient_ids:
        product = ingredients.get(ingredient_id)
        if product is None:
            continue
        wanted = need.get(ingredient_id, 0)
        have = on_hand.get((store.id, ingredient_id), 0)
        floor = reorder.get(ingredient_id, 0)
        short = max(wanted, floor) - have
        if short > 0 and (wanted > have or (floor > 0 and have <= floor)):
            known = supplier.get(ingredient_id)
            buckets["order"].append(
                _card(
                    "order",
                    "high" if have <= 0 or have < wanted else "medium",
                    f"Order {product.name}",
                    f"On hand {have}. The next {HORIZON_DAYS} days need {wanted}"
                    + (f", and the reorder point is {floor}" if floor else "")
                    + f". Buy {short}.",
                    product_id=ingredient_id,
                    store_id=store.id,
                    quantity=short,
                    supplier_name=known,
                    action="draft_purchase" if known else None,
                    href=None if known else _purchase_href(ingredient_id, store.id, short),
                )
            )
        elif wanted > 0:
            buckets["prep"].append(
                _card(
                    "prep",
                    "low",
                    f"Prep {product.name}",
                    f"Pull {wanted} for the next {HORIZON_DAYS} days. {have} is on hand at {store.name}.",
                    product_id=ingredient_id,
                    store_id=store.id,
                    quantity=wanted,
                    href="/inventory/recipes",
                )
            )

    expiring = expiry_service._rows(db, store_id=store.id, days=EXPIRY_DAYS)
    soonest: dict[uuid.UUID, int] = {}
    for row in expiring:
        product = ingredients.get(row.product_id)
        name = product.name if product else row.product_name
        rate = daily.get(row.product_id, 0)
        cover = rate * max(row.days_left, 0)
        if row.expired:
            kind, severity = "write_off", "high"
            title = f"Write off {name}"
            body = (
                f"{row.quantity_remaining} left on batch {row.batch_number}. "
                f"It expired {abs(row.days_left)} day{'s' if abs(row.days_left) != 1 else ''} ago."
            )
            action = "write_off"
        elif rate <= 0 or row.quantity_remaining > cover:
            kind, severity = "push_today", "high"
            title = f"Push {name} today"
            body = (
                f"{row.quantity_remaining} on batch {row.batch_number} expires in {row.days_left} day"
                f"{'s' if row.days_left != 1 else ''}, and recent sales will not use it in time."
            )
            action = None
        else:
            kind, severity = "use_first", "medium"
            title = f"Use {name} first"
            body = (
                f"Batch {row.batch_number} expires in {row.days_left} day{'s' if row.days_left != 1 else ''}. "
                f"{row.quantity_remaining} left, and the next service should sell through it."
            )
            action = None
        buckets[kind].append(
            _card(
                kind,
                severity,
                title,
                body,
                product_id=row.product_id,
                batch_item_id=row.batch_item_id,
                store_id=store.id,
                quantity=row.quantity_remaining,
                action=action,
                href=None if action else "/inventory/expiring",
            )
        )
        if row.days_left >= 0:
            soonest[row.product_id] = min(soonest.get(row.product_id, row.days_left), row.days_left)

    portions = fnb_service.menu_portions(db, list(products), [store.id])
    for product_id, availability in portions.items():
        if availability.menu_status != "unavailable":
            continue
        dish = products[product_id]
        limiting = ", ".join(availability.limiting) or "an ingredient"
        buckets["cannot_make"].append(
            _card(
                "cannot_make",
                "high",
                f"Cannot make {dish.name}",
                f"Take it off the menu until {limiting} is back in stock.",
                product_id=product_id,
                store_id=store.id,
                href="/inventory/recipes",
            )
        )

    for ingredient_id in ingredient_ids:
        product = ingredients.get(ingredient_id)
        if product is None:
            continue
        wanted = need.get(ingredient_id, 0)
        have = on_hand.get((store.id, ingredient_id), 0)
        floor = reorder.get(ingredient_id, 0)
        short = max(wanted, floor) - have
        if short <= 0:
            continue
        source = _surplus_store(db, on_hand, recipes, ingredient_id, store.id, short)
        if source is None:
            continue
        source_store, quantity = source
        buckets["transfer"].append(
            _card(
                "transfer",
                "medium",
                f"Move {product.name} from {source_store.name}",
                f"{store.name} is short {short}. {source_store.name} can send {quantity}.",
                product_id=ingredient_id,
                store_id=store.id,
                source_store_id=source_store.id,
                quantity=quantity,
                action="draft_transfer",
            )
        )

    today = datetime.now(UTC).date()
    variance = recipe_service.usage_variance(db, start=today - timedelta(days=WASTE_DAYS), end=today, store_id=store.id)
    for row in variance.rows:
        if row.theoretical <= 0 or row.variance <= 0:
            continue
        if row.variance * 100 < row.theoretical * WASTE_PERCENT:
            continue
        buckets["waste"].append(
            _card(
                "waste",
                "medium",
                f"{row.name} used more than the recipe",
                f"The last {WASTE_DAYS} days drew {row.actual} against {row.theoretical} the recipes call for.",
                product_id=row.ingredient_id,
                store_id=store.id,
                quantity=row.variance,
                href="/inventory/recipe-usage",
            )
        )

    global_bps, by_category, by_product = margin_service.active_policies(db)
    if (global_bps, by_category, by_product) != (None, {}, {}):
        for recipe in recipes:
            dish = products.get(recipe.product_id)
            if dish is None:
                continue
            bps = by_product.get(dish.id)
            if bps is None and dish.category_id is not None:
                bps = by_category.get(dish.category_id)
            if bps is None:
                bps = global_bps
            if bps is None:
                continue
            cooked = recipe_service.recipe_out(db, dish, recipe)
            if cooked.margin_bps is None or cooked.margin_bps >= bps:
                continue
            buckets["margin"].append(
                _card(
                    "margin",
                    "medium",
                    f"{dish.name} is under the margin floor",
                    f"Ingredient cost leaves a {cooked.margin_bps / 100:g}% margin. The floor is {bps / 100:g}%.",
                    product_id=dish.id,
                    store_id=store.id,
                    href="/inventory/recipes",
                )
            )

    for ingredient_id, days_left in soonest.items():
        product = ingredients.get(ingredient_id)
        if product is None or days_left < 0:
            continue
        have = on_hand.get((store.id, ingredient_id), 0)
        rate = daily.get(ingredient_id, 0)
        if rate <= 0:
            continue
        cover = rate * max(days_left, 1)
        if have <= cover:
            continue
        buckets["overstock"].append(
            _card(
                "overstock",
                "low",
                f"Too much {product.name}",
                f"{have} on hand will not be used before the batch that expires in {days_left} day"
                f"{'s' if days_left != 1 else ''}. Order less next time.",
                product_id=ingredient_id,
                store_id=store.id,
                quantity=have,
            )
        )

    ordered = (
        "order",
        "use_first",
        "push_today",
        "write_off",
        "cannot_make",
        "prep",
        "transfer",
        "waste",
        "margin",
        "overstock",
    )
    cards: list[KitchenCard] = []
    for kind in ordered:
        cards.extend(buckets[kind][:CARD_CAP])
    return cards


def _sold_portions(db: Session, store_id: uuid.UUID) -> dict[uuid.UUID, int]:
    since = datetime.combine(datetime.now(UTC).date() - timedelta(days=LOOKBACK_DAYS), time.min, UTC)
    rows = db.execute(
        select(SaleItem.product_id, func.sum(SaleItem.quantity))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.store_id == store_id, Sale.status.in_(POSTED), Sale.created_at >= since)
        .group_by(SaleItem.product_id)
    )
    return {product_id: int(total) for product_id, total in rows}


def _ingredient_need_raw(recipes: list[Recipe], sold: dict[uuid.UUID, int]) -> dict[uuid.UUID, int]:
    """Ingredient units the sold dishes call for, before scaling to the horizon."""
    wanted: dict[uuid.UUID, int] = defaultdict(int)
    for recipe in recipes:
        portions = sold.get(recipe.product_id, 0)
        if portions <= 0 or recipe.yield_quantity <= 0:
            continue
        for line in recipe.lines:
            wanted[line.ingredient_id] += (portions * line.quantity) // recipe.yield_quantity
    return wanted


def _ingredient_need(recipes: list[Recipe], sold: dict[uuid.UUID, int]) -> dict[uuid.UUID, int]:
    """Ingredient units for the next horizon, from the lookback rate of dish sales."""
    raw = _ingredient_need_raw(recipes, sold)
    return {ingredient_id: (quantity * HORIZON_DAYS) // LOOKBACK_DAYS for ingredient_id, quantity in raw.items()}


def _on_hand(db: Session, store_id: uuid.UUID | None) -> dict[tuple[uuid.UUID, uuid.UUID], int]:
    statement = select(InventoryLevel)
    if store_id is not None:
        statement = statement.where(InventoryLevel.store_id == store_id)
    found: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    for level in db.scalars(statement):
        found[(level.store_id, level.product_id)] = max(0, level.quantity_on_hand - level.quantity_reserved)
    return found


def _reorder(db: Session, store_id: uuid.UUID) -> dict[uuid.UUID, int]:
    rows = db.scalars(select(InventoryLevel).where(InventoryLevel.store_id == store_id))
    return {level.product_id: level.min_reorder_level for level in rows}


def _suppliers(db: Session, product_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not product_ids:
        return {}
    rows = db.execute(
        select(PurchaseOrderLine.product_id, PurchaseOrder.supplier_name)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(PurchaseOrderLine.product_id.in_(product_ids), PurchaseOrder.supplier_name != "")
        .order_by(PurchaseOrder.created_at.desc())
    )
    found: dict[uuid.UUID, str] = {}
    for product_id, name in rows:
        found.setdefault(product_id, name)
    return found


def _surplus_store(
    db: Session,
    on_hand: dict[tuple[uuid.UUID, uuid.UUID], int],
    recipes: list[Recipe],
    ingredient_id: uuid.UUID,
    store_id: uuid.UUID,
    short: int,
) -> tuple[Store, int] | None:
    stores = {
        store.id: store
        for store in db.scalars(select(Store).where(Store.is_active.is_(True), Store.id != store_id))
    }
    best: tuple[Store, int] | None = None
    for other_id, store in stores.items():
        have = on_hand.get((other_id, ingredient_id), 0)
        other_sold = _sold_portions(db, other_id)
        other_need = _ingredient_need(recipes, other_sold).get(ingredient_id, 0)
        other_floor = 0
        level = db.scalar(
            select(InventoryLevel).where(
                InventoryLevel.store_id == other_id, InventoryLevel.product_id == ingredient_id
            )
        )
        if level is not None:
            other_floor = level.min_reorder_level
        surplus = have - max(other_need, other_floor)
        if surplus < 1:
            continue
        quantity = min(short, surplus)
        if best is None or quantity > best[1]:
            best = (store, quantity)
    return best


def _purchase_href(product_id: uuid.UUID, store_id: uuid.UUID, quantity: int) -> str:
    return f"/inventory/purchase-orders?product={product_id}&quantity={quantity}&store={store_id}"


def _card(
    kind: str,
    severity: str,
    title: str,
    body: str,
    *,
    product_id: uuid.UUID | None = None,
    batch_item_id: uuid.UUID | None = None,
    store_id: uuid.UUID | None = None,
    source_store_id: uuid.UUID | None = None,
    quantity: int | None = None,
    supplier_name: str | None = None,
    action: str | None = None,
    href: str | None = None,
) -> KitchenCard:
    identity = ":".join(
        part
        for part in (
            kind,
            str(product_id or ""),
            str(batch_item_id or ""),
            str(store_id or ""),
        )
        if part
    )
    return KitchenCard(
        id=identity,
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        title=title,
        body=body,
        product_id=product_id,
        batch_item_id=batch_item_id,
        store_id=store_id,
        source_store_id=source_store_id,
        quantity=quantity,
        supplier_name=supplier_name,
        action=action,  # type: ignore[arg-type]
        href=href,
    )


def _draft_purchase(db: Session, principal: Principal, data: KitchenActionIn) -> KitchenActionOut:
    if data.product_id is None or data.store_id is None or data.quantity is None:
        raise ApiError(422, "invalid_request", "A purchase needs a product, a store, and a quantity.")
    name = (data.supplier_name or "").strip()
    if len(name) < 2:
        raise ApiError(422, "supplier_unknown", "No supplier is on file for this ingredient.")
    order = inventory.create_purchase_order(
        db,
        principal,
        PurchaseOrderCreate(
            supplier_name=name,
            destination_store_id=data.store_id,
            notes="Drafted from the kitchen brief.",
            lines=[PurchaseOrderLineIn(product_id=data.product_id, quantity_ordered=data.quantity)],
        ),
    )
    return KitchenActionOut(action="draft_purchase", reference=order.number, href="/inventory/purchase-orders")


def _draft_transfer(db: Session, settings: Settings, principal: Principal, data: KitchenActionIn) -> KitchenActionOut:
    if data.product_id is None or data.store_id is None or data.source_store_id is None or data.quantity is None:
        raise ApiError(422, "invalid_request", "A transfer needs a product, two stores, and a quantity.")
    transfer = inventory.create_transfer(
        db,
        settings,
        principal,
        TransferCreate(
            source_store_id=data.source_store_id,
            destination_store_id=data.store_id,
            note="Drafted from the kitchen brief.",
            lines=[TransferLineIn(product_id=data.product_id, quantity=data.quantity)],
        ),
    )
    return KitchenActionOut(action="draft_transfer", reference=transfer.number, href="/inventory/transfers")


def _write_off(db: Session, principal: Principal, data: KitchenActionIn) -> KitchenActionOut:
    if data.batch_item_id is None:
        raise ApiError(422, "invalid_request", "A write-off needs the batch line.")
    result = expiry_service.write_off(
        db,
        principal,
        ExpiryWriteOff(batch_item_id=data.batch_item_id, quantity=data.quantity, note="Kitchen brief write-off."),
    )
    return KitchenActionOut(
        action="write_off",
        reference=str(result.batch_item_id),
        href="/inventory/expiring",
    )
