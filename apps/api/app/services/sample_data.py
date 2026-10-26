"""Sample products and customers for a store in practice mode, so the owner can ring up a sale right away.

Everything loaded here is flagged is_sample; Go live deletes it. Food & beverage stores also get a floor plan and
kitchen stations, which Go live keeps as the store's real layout."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.product import Product
from app.models.store import Store
from app.schemas.payloads import SyncEventIn, SyncPushRequest
from app.schemas.wholesale import CustomerWrite
from app.services import customer_service
from app.services.identifiers import is_valid_imei
from app.services.item_type import PACKAGED_SAMPLE_SKUS
from app.services.settings_service import business_currency
from app.services.sync_service import push_batch

SAMPLE_IMEI_PREFIX = "35000000"


def samples_path() -> Path:
    return Path(__file__).resolve().parents[4] / "packages" / "catalog" / "samples.json"


def sample_imeis(count: int, seed: int) -> list[str]:
    """Luhn-valid IMEIs in a range no real handset uses."""
    found: list[str] = []
    body = seed * 1000
    while len(found) < count:
        stem = f"{SAMPLE_IMEI_PREFIX}{body:06d}"[:14]
        for digit in range(10):
            if is_valid_imei(f"{stem}{digit}"):
                found.append(f"{stem}{digit}")
                break
        body += 1
    return found


def _event(entity: str, payload: dict) -> SyncEventIn:
    return SyncEventIn(
        idempotency_key=f"sample:{entity}:{payload['id']}",
        entity_type=entity,  # type: ignore[arg-type]
        operation="upsert",
        payload=payload,
        occurred_at=datetime.now(UTC),
    )


def _grid(index: int, shape: str) -> tuple[int, int, int, int]:
    """Lays tables out four to a row on the floor-plan grid; long tables take a wider cell."""
    wide = shape == "rect"
    return (index % 4) * 4, (index // 4) * 4, 3 if wide else 2, 2


def load_food_kit(db: Session, settings: Settings, *, profile: str, sample: bool = True) -> int:
    """A restaurant, cafe or quick-service starter kit: menu, modifiers, meals, kitchen stations, and (where the
    business seats guests) a floor plan. Menu items, groups and meals are flagged as samples so Go live removes them;
    the floor plan and stations are the store's real layout to edit. Returns how many menu items were added."""
    from app.core.capabilities import Capability
    from app.models.kitchen import KitchenStation
    from app.models.menu import ModifierGroup, ModifierOption, ProductModifierGroup
    from app.models.restaurant import DiningArea, DiningTable
    from app.schemas.menu import ComboIn, ComboOptionIn, ComboSlotIn
    from app.services import category_service, combo_service
    from app.services.settings_service import cached_settings

    kit = json.loads(samples_path().read_text(encoding="utf-8")).get(profile)
    store = db.scalar(select(Store).where(Store.is_warehouse.is_(False)).order_by(Store.created_at).limit(1))
    if kit is None or store is None:
        return 0
    skus = [item["sku"] for item in kit["products"]]
    if db.scalar(select(Product.id).where(Product.sku.in_(skus)).limit(1)) is not None:
        ensure_starter_pantry(db)
        return 0
    modules = set(cached_settings(db).capabilities)
    currency = business_currency(db)

    categories: dict[str, uuid.UUID] = {}

    def category(name: str) -> tuple[str, uuid.UUID]:
        if name not in categories:
            categories[name] = category_service.resolve_by_name(db, name, None)[0].id
        return name, categories[name]

    products: dict[str, Product] = {}
    for item in kit["products"]:
        name, category_id = category(item["category"])
        product = Product(
            sku=item["sku"],
            barcode=item["sku"],
            name=item["name"],
            category=name,
            category_id=category_id,
            price_cents=item["price_cents"],
            currency=currency,
            # Prepared dishes carry no stock. Canned drinks and water are tracked units.
            is_service=False,
            is_sample=sample,
            item_type="PRE_PACKAGED" if item["sku"] in PACKAGED_SAMPLE_SKUS else "MADE_TO_ORDER",
            is_stock_tracked=item["sku"] in PACKAGED_SAMPLE_SKUS,
        )
        db.add(product)
        products[item["sku"]] = product
    db.flush()

    for position, spec in enumerate(kit.get("modifier_groups", [])):
        group = ModifierGroup(
            name=spec["name"],
            min_select=spec["min"],
            max_select=spec["max"],
            position=position,
            is_active=True,
            is_sample=sample,
        )
        group.options = [
            ModifierOption(
                name=option["name"],
                price_delta_cents=option.get("price_cents", 0),
                is_default=option.get("default", False),
                is_active=True,
                position=index,
            )
            for index, option in enumerate(spec["options"])
        ]
        db.add(group)
        db.flush()
        for sku in spec["products"]:
            db.add(ProductModifierGroup(product_id=products[sku].id, group_id=group.id, position=position))

    meals = 0
    for spec in kit.get("combos", []):
        combo_service.create_combo(
            db,
            ComboIn(
                name=spec["name"],
                category=spec["category"],
                price_cents=spec["price_cents"],
                sku=spec["sku"],
                slots=[
                    ComboSlotIn(
                        name=slot["name"],
                        min_select=slot.get("min", 1),
                        max_select=slot.get("max", 1),
                        options=[
                            ComboOptionIn(
                                product_id=products[option["sku"]].id,
                                surcharge_cents=option.get("surcharge_cents", 0),
                                is_default=option.get("default", False),
                            )
                            for option in slot["options"]
                        ],
                    )
                    for slot in spec["slots"]
                ],
            ),
            is_sample=sample,
            commit=False,
        )
        meals += 1

    has_floor = db.scalar(select(DiningArea.id).where(DiningArea.store_id == store.id).limit(1)) is not None
    if Capability.TABLES in modules and not has_floor:
        for position, spec in enumerate(kit.get("areas", [])):
            area = DiningArea(store_id=store.id, name=spec["name"], position=position, is_active=True)
            db.add(area)
            db.flush()
            for index, table in enumerate(spec["tables"]):
                shape = table.get("shape", "square")
                x, y, w, h = _grid(index, shape)
                db.add(
                    DiningTable(
                        area_id=area.id,
                        label=table["label"],
                        seats=table["seats"],
                        shape=shape,
                        x=x,
                        y=y,
                        w=w,
                        h=h,
                        is_active=True,
                    )
                )

    has_stations = db.scalar(select(KitchenStation.id).where(KitchenStation.store_id == store.id).limit(1))
    if Capability.KDS in modules and has_stations is None:
        for position, spec in enumerate(kit.get("stations", [])):
            db.add(
                KitchenStation(
                    store_id=store.id,
                    name=spec["name"],
                    category_ids=[str(category(name)[1]) for name in spec.get("categories", [])],
                    is_default=spec.get("default", False),
                    print_tickets=False,
                    position=position,
                    is_active=True,
                )
            )

    for spec in kit.get("customers", []):
        customer = customer_service.new_customer(db, CustomerWrite(**spec))
        customer.is_sample = sample
    db.commit()
    ensure_starter_pantry(db)
    return len(products) + meals


# Dish SKU -> ingredient lines (sku, name, by weight, recipe qty, opening stock, reorder level).
_STARTER_RECIPES: dict[str, list[tuple[str, str, bool, int, int, int]]] = {
    "SAMPLE-BEEF-BURGER": [
        ("ING-BEEF-PATTY", "Beef patty", False, 1, 42, 12),
        ("ING-BURGER-BUN", "Burger bun", False, 1, 42, 12),
        ("ING-CHEESE", "Cheese", True, 50, 5_000, 500),
    ],
    "SAMPLE-CHICKEN-PASTA": [
        ("ING-PASTA", "Pasta", True, 120, 6_000, 1_000),
        ("ING-CHICKEN", "Chicken breast", True, 100, 3_000, 800),
        ("ING-CREAM", "Cooking cream", True, 40, 4_000, 400),
    ],
    "SAMPLE-QSR-BURGER": [
        ("ING-BEEF-PATTY", "Beef patty", False, 1, 42, 12),
        ("ING-BURGER-BUN", "Burger bun", False, 1, 42, 12),
    ],
    "SAMPLE-CAPPUCCINO": [
        ("ING-COFFEE-BEANS", "Coffee beans", True, 18, 2_000, 200),
        ("ING-MILK", "Milk", True, 150, 10_000, 1_000),
    ],
}

_PACKAGED_OPENING = {
    "SAMPLE-SOFT-DRINK": 48,
    "SAMPLE-WATER": 72,
    "SAMPLE-CAFE-WATER": 72,
    "SAMPLE-QSR-COLA": 48,
    "SAMPLE-QSR-ORANGE-SODA": 36,
    "SAMPLE-QSR-WATER": 72,
    "SAMPLE-QSR-APPLE-JUICE": 24,
}


def ensure_starter_pantry(db: Session) -> None:
    """Gives an F&B sample menu a real pantry: tracked ingredients, recipes, and bottled drinks.

    Idempotent. Retail tenants return immediately. Opening quantities are written once, the first time a
    packaged item or dish has no stock movement or recipe yet.
    """
    from sqlalchemy import exists, or_

    from app.core.capabilities import FOOD_AND_BEVERAGE
    from app.models.inventory import StockMovement
    from app.models.recipe import Recipe, RecipeLine
    from app.models.store import Store
    from app.services import category_service
    from app.services.inventory import move_stock
    from app.services.item_type import apply_item_type
    from app.services.settings_service import cached_settings

    if cached_settings(db).business_profile not in FOOD_AND_BEVERAGE:
        return
    dish_skus = list(_STARTER_RECIPES)
    pending_dish = db.scalar(
        select(Product.id)
        .where(
            Product.sku.in_(dish_skus),
            ~exists(select(Recipe.id).where(Recipe.product_id == Product.id)),
        )
        .limit(1)
    )
    pending_pack = db.scalar(
        select(Product.id)
        .where(
            Product.sku.in_(list(PACKAGED_SAMPLE_SKUS)),
            or_(
                Product.item_type != "PRE_PACKAGED",
                ~exists(select(StockMovement.id).where(StockMovement.product_id == Product.id)),
            ),
        )
        .limit(1)
    )
    if pending_dish is None and pending_pack is None:
        return

    stores = list(db.scalars(select(Store).where(Store.is_warehouse.is_(False), Store.is_active.is_(True))).all())
    currency = business_currency(db)
    ingredients: dict[str, Product] = {}
    wanted = [line[0] for lines in _STARTER_RECIPES.values() for line in lines]
    for product in db.scalars(select(Product).where(Product.sku.in_(wanted))).all():
        ingredients[product.sku] = product

    def ingredient(spec: tuple[str, str, bool, int, int, int], sample: bool) -> Product:
        sku, name, by_weight, _qty, opening, reorder = spec
        product = ingredients.get(sku)
        if product is None:
            category, _sub = category_service.resolve_by_name(db, "Ingredients", None)
            product = Product(
                sku=sku,
                barcode=sku,
                name=name,
                category=category.name,
                category_id=category.id,
                price_cents=0,
                currency=currency,
                sold_by_weight=by_weight,
                is_sample=sample,
            )
            db.add(product)
            db.flush()
            apply_item_type(db, product, "RAW_INGREDIENT")
            ingredients[sku] = product
            for store in stores:
                level = move_stock(
                    db,
                    product_id=product.id,
                    store_id=store.id,
                    quantity=opening,
                    movement_type="AUDIT_ADJUSTMENT",
                    reference_type="opening_balance",
                    reference_id=product.id,
                    note="Opening ingredient stock",
                )
                level.min_reorder_level = reorder
        return product

    if pending_dish is not None:
        dishes = {
            product.sku: product
            for product in db.scalars(select(Product).where(Product.sku.in_(dish_skus))).all()
        }
        for sku, lines in _STARTER_RECIPES.items():
            dish = dishes.get(sku)
            if dish is None or db.scalar(select(Recipe.id).where(Recipe.product_id == dish.id)):
                continue
            apply_item_type(db, dish, "MADE_TO_ORDER")
            recipe = Recipe(product_id=dish.id, yield_quantity=1)
            db.add(recipe)
            db.flush()
            for position, spec in enumerate(lines):
                item = ingredient(spec, dish.is_sample)
                db.add(RecipeLine(recipe_id=recipe.id, ingredient_id=item.id, quantity=spec[3], position=position))

    if pending_pack is not None:
        for product in db.scalars(select(Product).where(Product.sku.in_(list(PACKAGED_SAMPLE_SKUS)))).all():
            apply_item_type(db, product, "PRE_PACKAGED")
            opening = _PACKAGED_OPENING.get(product.sku, 24)
            for store in stores:
                moved = db.scalar(
                    select(StockMovement.id)
                    .where(StockMovement.product_id == product.id, StockMovement.store_id == store.id)
                    .limit(1)
                )
                if moved is not None:
                    continue
                level = move_stock(
                    db,
                    product_id=product.id,
                    store_id=store.id,
                    quantity=opening,
                    movement_type="AUDIT_ADJUSTMENT",
                    reference_type="opening_balance",
                    reference_id=product.id,
                    note="Opening packaged stock",
                )
                if not level.min_reorder_level:
                    level.min_reorder_level = 12
    db.commit()


PRACTICE_EXPIRY_NOTE = "Practice expiry batch"
_DEPARTMENT_KEYS = ("Produce", "Dairy", "Bakery", "Pantry")


def _finish_grocery(db: Session, store: Store) -> None:
    """Marks weighed practice produce, pins department keys, and gives milk one expiry batch.

    Opening stock is already on the ledger. The batch only records which of those units expire, so a
    second call does not move stock again.
    """
    from datetime import timedelta

    from app.models.batch import BatchItem, PurchaseBatch
    from app.models.category import Category
    from app.models.inventory import InventoryLevel
    from app.models.user import User
    from app.schemas.module_settings import resolve_module_settings
    from app.services.batch_ledger import today
    from app.services.settings_service import load_settings

    catalog = json.loads(samples_path().read_text(encoding="utf-8")).get("grocery") or {}
    for item in catalog.get("products", []):
        if not item.get("sold_by_weight"):
            continue
        product = db.scalar(select(Product).where(Product.sku == item["sku"]))
        if product is None:
            continue
        product.sold_by_weight = True
        product.plu_code = item.get("plu_code")
        product.tare_grams = int(item.get("tare_grams") or 0)

    settings_row = load_settings(db, lock=True)
    current = resolve_module_settings(settings_row.module_settings)
    if not current.department_keys.keys:
        keys = []
        for name in _DEPARTMENT_KEYS:
            category = db.scalar(select(Category).where(Category.name == name))
            if category is not None:
                keys.append({"category_id": str(category.id), "label": category.name})
        if keys:
            stored = current.model_dump(mode="json")
            stored["department_keys"] = {"keys": keys}
            settings_row.module_settings = stored

    milk = db.scalar(select(Product).where(Product.sku == "SAMPLE-MILK-1L"))
    if milk is None:
        return
    existing = db.scalar(select(PurchaseBatch.id).where(PurchaseBatch.notes == PRACTICE_EXPIRY_NOTE).limit(1))
    if existing is not None:
        return
    owner_id = db.scalar(select(User.id).limit(1))
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == milk.id, InventoryLevel.store_id == store.id)
    )
    quantity = level.quantity_on_hand if level is not None else 0
    if owner_id is None or quantity <= 0:
        return
    cost = milk.price_cents // 2
    batch = PurchaseBatch(
        batch_number="PRACTICE-MILK",
        store_id=store.id,
        import_source="MANUAL",
        total_cost_amount=cost * quantity,
        total_items_count=quantity,
        currency=milk.currency,
        status="ACTIVE",
        notes=PRACTICE_EXPIRY_NOTE,
        created_by_id=owner_id,
    )
    db.add(batch)
    db.flush()
    db.add(
        BatchItem(
            batch_id=batch.id,
            position=0,
            product_id=milk.id,
            store_id=store.id,
            quantity_imported=quantity,
            quantity_remaining=quantity,
            purchase_cost_per_unit=cost,
            selling_price_per_unit=milk.price_cents,
            expiry_date=today() + timedelta(days=7),
            imported_serials=[],
        )
    )


def load(db: Session, settings: Settings, *, profile: str, sub_type: str | None = None) -> int:
    """Loads the profile's sample items into the first store; returns how many products were added."""
    from app.core.capabilities import FOOD_AND_BEVERAGE

    if profile in FOOD_AND_BEVERAGE:
        return load_food_kit(db, settings, profile=profile)
    catalog = json.loads(samples_path().read_text(encoding="utf-8")).get(profile)
    store = db.scalar(select(Store).where(Store.is_warehouse.is_(False)).order_by(Store.created_at).limit(1))
    if catalog is None or store is None:
        return 0
    if db.scalar(select(Product.id).where(Product.is_sample.is_(True)).limit(1)) is not None:
        if profile == "grocery":
            _finish_grocery(db, store)
            db.commit()
        return 0
    currency = business_currency(db)
    events: list[SyncEventIn] = []
    product_ids: list[uuid.UUID] = []
    for index, item in enumerate(catalog["products"]):
        product_id = uuid.uuid4()
        product_ids.append(product_id)
        events.append(
            _event(
                "product",
                {
                    "id": str(product_id),
                    "store_id": str(store.id),
                    "sku": item["sku"],
                    "barcode": f"200000{index:06d}",
                    "name": item["name"],
                    "brand": item.get("brand"),
                    "category": item["category"],
                    "price_cents": item["price_cents"],
                    "currency": currency,
                    "is_serialized": item["is_serialized"],
                    "stock_quantity": 0 if item["is_serialized"] else item.get("stock", 0),
                },
            )
        )
        if item["is_serialized"]:
            for value in sample_imeis(item.get("units", 1), seed=index + 1):
                events.append(
                    _event(
                        "serial_number",
                        {
                            "id": str(uuid.uuid4()),
                            "product_id": str(product_id),
                            "store_id": str(store.id),
                            "kind": "imei",
                            "value": value,
                            "status": "in_stock",
                        },
                    )
                )
    push_batch(db, SyncPushRequest(device_id="signup-samples", events=events), settings, source="portal")
    db.execute(update(Product).where(Product.id.in_(product_ids)).values(is_sample=True))
    for spec in catalog.get("customers", []):
        customer = customer_service.new_customer(db, CustomerWrite(**spec))
        customer.is_sample = True
    if profile == "grocery":
        _finish_grocery(db, store)
    db.commit()
    return len(product_ids)
