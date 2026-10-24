"""Guest suggestions for restaurant and cafe checks.

Ranked from this guest's posted sales, dishes added in the last three weeks, and the store's upsell pairs.
Every dish is one already on the menu. Nothing here is added to an order or sent to the kitchen.
"""

from __future__ import annotations

import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.schemas.orders import GuestSuggestionOut, GuestSuggestionsOut
from app.schemas.payloads import ModifierChoice
from app.services import restaurant_insights_service
from app.services.settings_service import cached_settings

GUEST_PROFILES = frozenset({"restaurant", "cafe"})
HISTORY_DAYS = 90
NEW_DISH_DAYS = 21
LIMIT = 3
# Same words as the table menu, so a "Drinks" category and a beverage course stay one course.
_COURSE_WORDS = (
    ("Starters", ("starter", "appet", "soup", "salad")),
    ("Beverages", ("drink", "beverage", "coffee", "tea", "juice")),
    ("Desserts", ("dessert", "sweet", "cake")),
)
_MISSING_COURSES = ("Desserts", "Beverages", "Starters", "Mains")


def _course(category: str) -> str:
    text = category.lower()
    for name, words in _COURSE_WORDS:
        if any(word in text for word in words):
            return name
    return "Mains"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _sellable(product: Product) -> bool:
    return (
        product.item_type != "RAW_INGREDIENT"
        and not product.is_serialized
        and not product.sold_by_weight
        and not product.is_ingredient
    )


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only see your own store.")


def _modifier_key(raw: list | None) -> tuple[tuple[str, str, str, str, int], ...]:
    if not raw:
        return ()
    choices: list[tuple[str, str, str, str, int]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        group_id = str(item.get("group_id") or "")
        option_id = str(item.get("option_id") or "")
        if not group_id or not option_id:
            continue
        delta = item.get("price_delta_cents") or 0
        choices.append((group_id, option_id, str(item.get("group") or ""), str(item.get("option") or ""), int(delta)))
    choices.sort()
    return tuple(choices)


def _choices(key: tuple[tuple[str, str, str, str, int], ...]) -> list[ModifierChoice]:
    chosen: list[ModifierChoice] = []
    for group_id, option_id, group, option, delta in key:
        try:
            chosen.append(
                ModifierChoice(
                    group_id=uuid.UUID(group_id),
                    option_id=uuid.UUID(option_id),
                    group=group or None,
                    option=option or None,
                    price_delta_cents=delta,
                )
            )
        except ValueError:
            continue
    return chosen


def _join(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _usual_pitch(times: int, visits: int, names: list[str]) -> str:
    pitch = f"Ordered on {times} of the last {visits} visits"
    if names:
        pitch += f", usually with {_join(names)}"
    return f"{pitch}."


def _new_pitch(created_at: datetime, course: str, now: datetime) -> str:
    when = "New this week" if now - _aware(created_at) <= timedelta(days=7) else "New on the menu"
    return f"{when}, in {course}."


def _history(
    db: Session, customer_id: uuid.UUID, store_id: uuid.UUID, since: datetime
) -> tuple[int, Counter[str], list[tuple[Product, int, tuple[tuple[str, str, str, str, int], ...]]]]:
    rows = db.execute(
        select(Sale.id, SaleItem.product_id, SaleItem.modifiers)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.customer_id == customer_id,
            Sale.store_id == store_id,
            Sale.created_at >= since,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(restaurant_insights_service.POSTED),
        )
    ).all()
    visits: set[uuid.UUID] = set()
    by_product: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    modifiers: dict[uuid.UUID, Counter[tuple[tuple[str, str, str, str, int], ...]]] = defaultdict(Counter)
    counted: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for sale_id, product_id, raw in rows:
        visits.add(sale_id)
        by_product[product_id].add(sale_id)
        mark = (sale_id, product_id)
        if mark in counted:
            continue
        counted.add(mark)
        modifiers[product_id][_modifier_key(raw)] += 1
    if not by_product:
        return 0, Counter(), []
    products = {
        row.id: row for row in db.scalars(select(Product).where(Product.id.in_(list(by_product)))).unique()
    }
    courses: Counter[str] = Counter()
    ranked: list[tuple[Product, int, tuple[tuple[str, str, str, str, int], ...]]] = []
    for product_id, sale_ids in by_product.items():
        product = products.get(product_id)
        if product is None or not _sellable(product):
            continue
        times = len(sale_ids)
        courses[_course(product.category)] += times
        winner = modifiers[product_id].most_common(1)
        ranked.append((product, times, winner[0][0] if winner else ()))
    ranked.sort(key=lambda item: (-item[1], item[0].name))
    return len(visits), courses, ranked


def _new_dish(
    db: Session,
    *,
    now: datetime,
    exclude: set[uuid.UUID],
    favorite: str | None,
    present: set[str],
) -> Product | None:
    fresh = [
        product
        for product in db.scalars(
            select(Product)
            .where(
                Product.created_at >= now - timedelta(days=NEW_DISH_DAYS),
                Product.item_type != "RAW_INGREDIENT",
                Product.is_serialized.is_(False),
                Product.sold_by_weight.is_(False),
                Product.is_ingredient.is_(False),
            )
            .order_by(Product.created_at.desc())
            .limit(80)
        ).unique()
        if product.id not in exclude and _sellable(product)
    ]
    if not fresh:
        return None
    if favorite is not None:
        matched = [product for product in fresh if _course(product.category) == favorite]
        if matched:
            return matched[0]
    for course in _MISSING_COURSES:
        if course in present:
            continue
        matched = [product for product in fresh if _course(product.category) == course]
        if matched:
            return matched[0]
    return fresh[0]


def _card(
    product: Product,
    *,
    kind: Literal["usual", "new", "pair"],
    pitch: str,
    modifiers: list[ModifierChoice] | None = None,
) -> GuestSuggestionOut:
    return GuestSuggestionOut(
        product_id=product.id,
        name=product.name,
        price_cents=product.price_cents,
        currency=product.currency,
        kind=kind,
        pitch=pitch,
        modifiers=modifiers or [],
    )


def suggestions(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    product_ids: list[uuid.UUID],
) -> GuestSuggestionsOut:
    profile = cached_settings(db).business_profile
    if profile not in GUEST_PROFILES:
        raise ApiError(403, "forbidden", "Guest suggestions are only available for restaurant and cafe businesses.")
    _scope(principal, store_id)
    now = datetime.now(UTC)
    on_check = set(product_ids)
    visits = 0
    favorite: str | None = None
    usuals: list[tuple[Product, int, tuple[tuple[str, str, str, str, int], ...]]] = []
    if customer_id is not None:
        visits, courses, ranked = _history(db, customer_id, store_id, now - timedelta(days=HISTORY_DAYS))
        favorite = courses.most_common(1)[0][0] if courses else None
        usuals = [row for row in ranked if row[0].id not in on_check]

    present: set[str] = set()
    if on_check:
        present = {
            _course(product.category)
            for product in db.scalars(select(Product).where(Product.id.in_(on_check))).unique()
        }
    reserved = {product.id for product, _, _ in usuals[:2]}
    fresh = _new_dish(db, now=now, exclude=on_check | reserved, favorite=favorite, present=present)

    chosen: list[GuestSuggestionOut] = []
    for product, times, key in usuals[: 2 if fresh is not None else LIMIT]:
        modifiers = _choices(key)
        names = [choice.option for choice in modifiers if choice.option]
        chosen.append(_card(product, kind="usual", pitch=_usual_pitch(times, visits, names), modifiers=modifiers))
    if fresh is not None and len(chosen) < LIMIT:
        chosen.append(_card(fresh, kind="new", pitch=_new_pitch(fresh.created_at, _course(fresh.category), now)))
    if len(chosen) < LIMIT:
        taken = on_check | {item.product_id for item in chosen}
        report = restaurant_insights_service.upsell(
            db, principal, product_ids=list(on_check), store_id=store_id, limit=10
        )
        for pair in report.pairs:
            if pair.add_on_id in taken:
                continue
            product = db.get(Product, pair.add_on_id)
            if product is None or not _sellable(product):
                continue
            chosen.append(_card(product, kind="pair", pitch=pair.pitch))
            taken.add(product.id)
            if len(chosen) == LIMIT:
                break
    return GuestSuggestionsOut(suggestions=chosen[:LIMIT])
