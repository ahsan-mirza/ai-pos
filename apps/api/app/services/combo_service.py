"""Meal combos. A meal is a service product whose slots (Main, Side, Drink) each offer real menu items; the
cashier picks the parts, and every part routes to its own kitchen station and draws its own stock or recipe.

Registers cache the slots with the menu and send each line's picks; the server prices them from this catalogue
(names and surcharges in the payload are informational), exactly like modifiers."""

import uuid
from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError, SyncRejected
from app.models.category import Category
from app.models.menu import ComboSlot, ComboSlotOption
from app.models.product import Product
from app.schemas.menu import ComboIn, ComboOptionOut, ComboOut, ComboSlotOut
from app.schemas.payloads import ComboChoice
from app.services import category_service
from app.services.settings_service import business_currency


def slots_by_product(db: Session, product_ids: Iterable[uuid.UUID] | None = None) -> dict[uuid.UUID, list[ComboSlot]]:
    statement = select(ComboSlot).order_by(ComboSlot.position)
    if product_ids is not None:
        ids = list(product_ids)
        if not ids:
            return {}
        statement = statement.where(ComboSlot.product_id.in_(ids))
    out: dict[uuid.UUID, list[ComboSlot]] = defaultdict(list)
    for slot in db.scalars(statement):
        out[slot.product_id].append(slot)
    return dict(out)


def combo_ids(db: Session, product_ids: Iterable[uuid.UUID]) -> set[uuid.UUID]:
    ids = list(product_ids)
    if not ids:
        return set()
    return set(db.scalars(select(ComboSlot.product_id).where(ComboSlot.product_id.in_(ids)).distinct()).all())


def _products(db: Session, ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, Product]:
    wanted = list(set(ids))
    if not wanted:
        return {}
    return {product.id: product for product in db.scalars(select(Product).where(Product.id.in_(wanted)))}


def _slot_out(slot: ComboSlot, products: dict[uuid.UUID, Product]) -> ComboSlotOut:
    return ComboSlotOut(
        id=slot.id,
        name=slot.name,
        min_select=slot.min_select,
        max_select=slot.max_select,
        position=slot.position,
        options=[
            ComboOptionOut(
                product_id=option.product_id,
                name=products[option.product_id].name,
                category=products[option.product_id].category,
                price_cents=products[option.product_id].price_cents,
                surcharge_cents=option.surcharge_cents,
                is_default=option.is_default,
                position=option.position,
            )
            for option in slot.options
            if option.product_id in products
        ],
    )


def _component_ids(slots: Iterable[ComboSlot]) -> set[uuid.UUID]:
    return {option.product_id for slot in slots for option in slot.options}


def _combo_out(product: Product, slots: list[ComboSlot], products: dict[uuid.UUID, Product]) -> ComboOut:
    return ComboOut(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        category=product.category,
        category_id=product.category_id,
        price_cents=product.price_cents,
        tax_category=product.tax_category,
        slots=[_slot_out(slot, products) for slot in slots],
    )


def list_combos(db: Session) -> list[ComboOut]:
    by_product = slots_by_product(db)
    products = _products(db, [*by_product, *(_component_ids(s for slots in by_product.values() for s in slots))])
    combos = [
        _combo_out(products[product_id], slots, products) for product_id, slots in by_product.items()
        if product_id in products
    ]
    return sorted(combos, key=lambda combo: (combo.category.lower(), combo.name.lower()))


def get_combo(db: Session, product_id: uuid.UUID) -> ComboOut:
    product = db.get(Product, product_id)
    slots = slots_by_product(db, [product_id]).get(product_id, [])
    if product is None or not slots:
        raise ApiError(404, "not_found", "Meal was not found.")
    return _combo_out(product, slots, _products(db, _component_ids(slots)))


def _category(db: Session, data: ComboIn) -> Category:
    if data.category_id is not None:
        category = db.get(Category, data.category_id)
        if category is None:
            raise ApiError(422, "unknown_category", "Category does not exist.")
        return category
    assert data.category is not None
    return category_service.resolve_by_name(db, data.category, None)[0]


def _check_components(db: Session, combo_id: uuid.UUID | None, data: ComboIn) -> None:
    wanted = {option.product_id for slot in data.slots for option in slot.options}
    found = _products(db, wanted)
    missing = wanted - found.keys()
    if missing:
        raise ApiError(422, "unknown_product", "A meal item does not exist.")
    if combo_id is not None and combo_id in wanted:
        raise ApiError(422, "invalid_request", "A meal cannot contain itself.")
    nested = combo_ids(db, wanted)
    for product in found.values():
        if product.id in nested:
            raise ApiError(422, "invalid_request", f"{product.name} is a meal itself; meals cannot be nested.")
        if product.is_serialized or product.sold_by_weight or product.is_open_price or product.is_ingredient:
            raise ApiError(
                422,
                "invalid_request",
                f"{product.name} cannot be part of a meal (serialized, weighed, open-price and ingredient items).",
            )


def _check_meal_product(db: Session, product: Product) -> None:
    if product.is_serialized or product.sold_by_weight or product.is_open_price or product.is_ingredient:
        raise ApiError(422, "invalid_request", "Serialized, weighed, open-price and ingredient items cannot be meals.")
    used = db.scalar(select(ComboSlotOption.id).where(ComboSlotOption.product_id == product.id).limit(1))
    if used is not None:
        raise ApiError(422, "invalid_request", f"{product.name} is part of another meal; meals cannot be nested.")


def _replace_slots(db: Session, product: Product, data: ComboIn) -> None:
    db.execute(delete(ComboSlot).where(ComboSlot.product_id == product.id))
    db.flush()
    for position, item in enumerate(data.slots):
        slot = ComboSlot(
            product_id=product.id,
            name=item.name.strip(),
            min_select=item.min_select,
            max_select=item.max_select,
            position=position,
        )
        slot.options = [
            ComboSlotOption(
                product_id=option.product_id,
                surcharge_cents=option.surcharge_cents,
                is_default=option.is_default,
                position=index,
            )
            for index, option in enumerate(item.options)
        ]
        db.add(slot)


def _new_sku(db: Session) -> str:
    while True:
        sku = f"MEAL-{uuid.uuid4().hex[:8].upper()}"
        if db.scalar(select(Product.id).where((Product.sku == sku) | (Product.barcode == sku))) is None:
            return sku


def create_combo(db: Session, data: ComboIn, *, is_sample: bool = False, commit: bool = True) -> ComboOut:
    _check_components(db, None, data)
    sku = data.sku.strip() if data.sku else _new_sku(db)
    if db.scalar(select(Product.id).where((Product.sku == sku) | (Product.barcode == sku))) is not None:
        raise ApiError(409, "conflict", "SKU is already in use.")
    category = _category(db, data)
    product = Product(
        sku=sku,
        barcode=sku,
        name=data.name.strip(),
        category=category.name,
        category_id=category.id,
        price_cents=data.price_cents,
        currency=business_currency(db),
        tax_category=data.tax_category,
        is_service=True,
        is_sample=is_sample,
    )
    db.add(product)
    db.flush()
    _replace_slots(db, product, data)
    if commit:
        db.commit()
    else:
        db.flush()
    return get_combo(db, product.id)


def update_combo(db: Session, product_id: uuid.UUID, data: ComboIn) -> ComboOut:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Meal was not found.")
    _check_meal_product(db, product)
    _check_components(db, product.id, data)
    category = _category(db, data)
    product.name = data.name.strip()
    product.category, product.category_id, product.sub_category_id = category.name, category.id, None
    product.price_cents = data.price_cents
    product.tax_category = data.tax_category
    product.is_service = True
    _replace_slots(db, product, data)
    db.commit()
    return get_combo(db, product.id)


def remove_combo(db: Session, product_id: uuid.UUID) -> None:
    """The item stays on the menu as a plain service item; past sale lines keep their component snapshot."""
    if not slots_by_product(db, [product_id]):
        raise ApiError(404, "not_found", "Meal was not found.")
    db.execute(delete(ComboSlot).where(ComboSlot.product_id == product_id))
    db.commit()


def register_combos(db: Session) -> dict[str, list[ComboSlotOut]]:
    by_product = slots_by_product(db)
    products = _products(db, _component_ids(slot for slots in by_product.values() for slot in slots))
    return {str(product_id): [_slot_out(slot, products) for slot in slots] for product_id, slots in by_product.items()}


def price_components(
    db: Session, product: Product, components: list[ComboChoice]
) -> tuple[int, list[dict] | None]:
    """The surcharge total of a meal's picks and the snapshot stored on the line.

    Rejects picks outside the meal's slots and selections outside a slot's minimum/maximum. Surcharges come from
    the catalogue, never from the payload."""
    slots = slots_by_product(db, [product.id]).get(product.id, [])
    if not slots:
        if components:
            raise SyncRejected(f"{product.name} is not a meal.")
        return 0, None
    by_id = {slot.id: slot for slot in slots}
    picked: dict[uuid.UUID, list[ComboSlotOption]] = defaultdict(list)
    for choice in components:
        slot = by_id.get(choice.slot_id)
        option = next((item for item in slot.options if item.product_id == choice.product_id), None) if slot else None
        if slot is None or option is None:
            raise SyncRejected(f"A choice on {product.name} is not part of this meal.")
        if option in picked[slot.id]:
            raise SyncRejected(f"An item was picked twice on {product.name}.")
        picked[slot.id].append(option)
    for slot in slots:
        count = len(picked.get(slot.id, []))
        if count < slot.min_select:
            raise SyncRejected(f"{product.name} needs a choice of {slot.name}.")
        if count > slot.max_select:
            raise SyncRejected(f"{product.name} allows at most {slot.max_select} {slot.name}.")
    names = _products(db, [option.product_id for options in picked.values() for option in options])
    snapshot = [
        {
            "slot_id": str(slot.id),
            "slot": slot.name,
            "product_id": str(option.product_id),
            "name": names[option.product_id].name if option.product_id in names else "",
            "surcharge_cents": option.surcharge_cents,
        }
        for slot in slots
        for option in picked.get(slot.id, [])
    ]
    return sum(option.surcharge_cents for options in picked.values() for option in options), snapshot or None


def component_ids(snapshot: list[dict] | None) -> list[uuid.UUID]:
    """Component product ids of a stored line snapshot, in slot order."""
    return [uuid.UUID(str(item["product_id"])) for item in snapshot or [] if item.get("product_id")]
