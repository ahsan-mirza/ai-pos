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
            # Made to order: no stock of its own until a recipe draws ingredients.
            is_service=True,
            is_sample=sample,
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
    return len(products) + meals


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
    db.commit()
    return len(product_ids)
