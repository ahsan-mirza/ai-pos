"""Grocery till extras: the bag-fee service product and co-purchase suggestions.

Suggestions are ranked from this store's own posted sales. A thin history or a failed lookup returns nothing.
Nothing here adds a line to a sale.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.cache import get_value, set_value
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.module_settings import BagSettings
from app.schemas.orders import GuestSuggestionOut, GuestSuggestionsOut
from app.services.settings_service import business_currency, cached_settings

BAG_SKU = "BAG-FEE"
HISTORY_DAYS = 90
MIN_TOGETHER = 3
LIMIT = 3
CACHE_SECONDS = 60


def ensure_bag_product(db: Session, bags: BagSettings) -> Product:
    """The service product a cashier sells when they add a bag. Stock is never tracked."""
    product = db.scalar(select(Product).where(Product.sku == BAG_SKU))
    if product is None:
        product = Product(
            sku=BAG_SKU,
            barcode=BAG_SKU,
            name="Bag",
            category="Household",
            price_cents=bags.fee_cents,
            currency=business_currency(db),
            is_service=True,
            is_stock_tracked=False,
            tax_category=bags.tax_category,
        )
        db.add(product)
        db.flush()
    else:
        product.price_cents = bags.fee_cents
        product.tax_category = bags.tax_category
        product.is_service = True
        product.is_stock_tracked = False
    existing = set(
        db.scalars(select(InventoryLevel.store_id).where(InventoryLevel.product_id == product.id)).all()
    )
    for store_id in db.scalars(select(Store.id)):
        if store_id in existing:
            continue
        db.add(InventoryLevel(product_id=product.id, store_id=store_id, quantity_on_hand=0, quantity_reserved=0))
    return product


def _scope(principal: Principal, store_id: uuid.UUID) -> None:
    if principal.store_id is not None and principal.store_id != store_id:
        raise ApiError(403, "store_scope", "You can only see your own store.")


def suggestions(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> GuestSuggestionsOut:
    """Up to three products bought with this basket. Grocery only. The caller still adds the line."""
    if cached_settings(db).business_profile != "grocery":
        raise ApiError(403, "wrong_profile", "Basket suggestions are for grocery stores.")
    _scope(principal, store_id)
    basket = list(dict.fromkeys(product_ids))
    if not basket:
        return GuestSuggestionsOut(suggestions=[])
    from app.tenancy.context import current_tenant

    tenant = current_tenant()
    tenant_id = tenant.id if tenant is not None else "local"
    # The newest sale at this store changes the key, so a sale just posted is not hidden by the cache.
    posted = db.scalar(
        select(func.count(Sale.id)).where(Sale.store_id == store_id, Sale.status == "completed")
    )
    key = f"grocery-pairs:{tenant_id}:{store_id}:{posted}:{','.join(sorted(str(item) for item in basket))}"
    cached = get_value(key)
    if cached:
        try:
            return GuestSuggestionsOut.model_validate(json.loads(cached))
        except ValueError:
            pass
    found = _rank(db, store_id, basket)
    payload = GuestSuggestionsOut(suggestions=found)
    set_value(key, payload.model_dump_json(), CACHE_SECONDS)
    return payload


def _rank(db: Session, store_id: uuid.UUID, basket: list[uuid.UUID]) -> list[GuestSuggestionOut]:
    since = datetime.now(UTC) - timedelta(days=HISTORY_DAYS)
    # One SaleItem in each statement. A self-join of the same table is ambiguous once tenant
    # scope adds its own predicate, so the basket sales are a subquery.
    matching = (
        select(Sale.id.label("sale_id"))
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.status == "completed",
            Sale.is_quote_proforma.is_(False),
            Sale.created_at >= since,
            SaleItem.product_id.in_(basket),
        )
        .distinct()
        .subquery()
    )
    counts = dict(
        db.execute(
            select(SaleItem.product_id, func.count(func.distinct(SaleItem.sale_id)))
            .join(matching, matching.c.sale_id == SaleItem.sale_id)
            .where(SaleItem.product_id.notin_(basket))
            .group_by(SaleItem.product_id)
            .having(func.count(func.distinct(SaleItem.sale_id)) >= MIN_TOGETHER)
            .order_by(func.count(func.distinct(SaleItem.sale_id)).desc())
            .limit(12)
        ).all()
    )
    if not counts:
        return []
    live = cached_settings(db).live_at is not None
    products = {
        product.id: product
        for product in db.scalars(select(Product).where(Product.id.in_(counts))).all()
    }
    stock = dict(
        db.execute(
            select(
                InventoryLevel.product_id,
                InventoryLevel.quantity_on_hand - InventoryLevel.quantity_reserved,
            ).where(
                InventoryLevel.store_id == store_id,
                InventoryLevel.product_id.in_(counts),
            )
        ).all()
    )
    ranked: list[GuestSuggestionOut] = []
    for product_id, _times in sorted(counts.items(), key=lambda item: item[1], reverse=True):
        product = products.get(product_id)
        if product is None or product.price_cents <= 0:
            continue
        if product.is_ingredient or product.is_service or product.sku == BAG_SKU:
            continue
        if live and product.is_sample:
            continue
        if product.is_stock_tracked and stock.get(product_id, 0) <= 0:
            continue
        ranked.append(
            GuestSuggestionOut(
                product_id=product.id,
                name=product.name,
                price_cents=product.price_cents,
                currency=product.currency,
                kind="pair",
                pitch="Frequently bought together.",
            )
        )
        if len(ranked) == LIMIT:
            break
    return ranked
