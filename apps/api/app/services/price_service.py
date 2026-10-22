"""Price tier administration: the retail vs wholesale matrix, per-product tier rows, and bulk rules."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.product import Product
from app.models.product_price import ProductPrice
from app.schemas.payloads import VolumeBreak
from app.schemas.wholesale import (
    BulkPriceResult,
    BulkPriceUpdate,
    PricingMatrix,
    PricingRow,
    ProductPricingWrite,
)
from app.services import uom_service
from app.services.inventory import price_out
from app.services.pricing import TIER_ORDER
from app.services.settings_service import business_currency


def _row(product: Product) -> PricingRow:
    return PricingRow(
        product_id=product.id,
        sku=product.sku,
        name=product.name,
        brand=product.brand,
        category=product.category,
        category_id=product.category_id,
        is_serialized=product.is_serialized,
        retail_price_cents=product.price_cents,
        min_order_quantity=product.min_order_quantity,
        sellable_units=product.sellable_units or ["PIECE"],  # type: ignore[arg-type]
        prices=sorted((price_out(row) for row in product.prices), key=lambda item: TIER_ORDER.index(item.price_tier)),
    )


def matrix(
    db: Session,
    *,
    category_id: uuid.UUID | None,
    brand: str | None,
    query: str | None,
    limit: int,
) -> PricingMatrix:
    statement = select(Product).order_by(Product.category, Product.name).limit(limit)
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if brand:
        statement = statement.where(func.lower(func.coalesce(Product.brand, "")) == brand.strip().lower())
    if query:
        like = f"%{query.strip().lower()}%"
        statement = statement.where(func.lower(Product.name).like(like) | func.lower(Product.sku).like(like))
    brands = [
        row[0]
        for row in db.execute(
            select(Product.brand).where(Product.brand.is_not(None)).distinct().order_by(Product.brand)
        ).all()
    ]
    return PricingMatrix(
        currency=business_currency(db),
        rows=[_row(product) for product in db.scalars(statement).unique().all()],
        brands=brands,
    )


def _breaks(items: list[VolumeBreak]) -> list[dict[str, int]]:
    return [{"min_qty": item.min_qty, "price_cents": item.price_cents} for item in items]


def _tier_row(product: Product, tier: str) -> ProductPrice | None:
    return next((row for row in product.prices if row.price_tier == tier), None)


def update_product_pricing(db: Session, product_id: uuid.UUID, data: ProductPricingWrite) -> PricingRow:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product was not found.")
    if data.retail_price_cents is not None:
        product.price_cents = data.retail_price_cents
    if data.min_order_quantity is not None:
        product.min_order_quantity = data.min_order_quantity
    if data.sellable_units is not None:
        product.sellable_units = uom_service.check_sellable(
            db, data.sellable_units, serialized=product.is_serialized, weighed=product.sold_by_weight
        )
    for tier in data.tiers:
        row = _tier_row(product, tier.price_tier)
        keeps_row = tier.price_cents is not None or (tier.price_tier == "RETAIL" and tier.volume_discounts)
        if not keeps_row:
            if row is not None:
                product.prices.remove(row)
            continue
        price = tier.price_cents if tier.price_tier != "RETAIL" or tier.price_cents is not None else product.price_cents
        if tier.price_tier == "RETAIL" and tier.price_cents is not None:
            product.price_cents = tier.price_cents
        if row is None:
            row = ProductPrice(product_id=product.id, price_tier=tier.price_tier)
            product.prices.append(row)
        row.price_cents = int(price or 0)
        row.min_order_quantity = tier.min_order_quantity
        row.volume_discounts = _breaks(tier.volume_discounts)
    db.commit()
    db.refresh(product)
    return _row(product)


def bulk_update(db: Session, data: BulkPriceUpdate) -> BulkPriceResult:
    statement = select(Product)
    if data.product_ids is not None:
        statement = statement.where(Product.id.in_(data.product_ids))
    if data.category_id is not None:
        statement = statement.where(Product.category_id == data.category_id)
    if data.brand:
        statement = statement.where(func.lower(func.coalesce(Product.brand, "")) == data.brand.strip().lower())
    products = list(db.scalars(statement).unique().all())
    updated = skipped = 0
    for product in products:
        row = _tier_row(product, data.price_tier)
        current = (
            product.price_cents
            if data.price_tier == "RETAIL"
            else (row.price_cents if row is not None else product.price_cents)
        )
        if data.mode == "set":
            price = int(data.price_cents or 0)
        elif data.mode == "percent_of_retail":
            price = round(product.price_cents * int(data.percent_bps or 0) / 10_000)
        else:
            price = round(current * (10_000 + int(data.percent_bps or 0)) / 10_000)
        if price < 0:
            skipped += 1
            continue
        if data.price_tier == "RETAIL":
            product.price_cents = price
            if row is None and (data.volume_discounts or data.min_order_quantity):
                row = ProductPrice(
                    product_id=product.id, price_tier="RETAIL", min_order_quantity=1, volume_discounts=[]
                )
                product.prices.append(row)
        elif row is None:
            row = ProductPrice(
                product_id=product.id, price_tier=data.price_tier, min_order_quantity=1, volume_discounts=[]
            )
            product.prices.append(row)
        if row is not None:
            row.price_cents = price
            if data.min_order_quantity is not None:
                row.min_order_quantity = data.min_order_quantity
            if data.volume_discounts is not None:
                row.volume_discounts = _breaks(data.volume_discounts)
        updated += 1
    db.commit()
    return BulkPriceResult(updated=updated, skipped=skipped)
