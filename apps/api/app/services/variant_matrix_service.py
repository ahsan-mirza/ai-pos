"""Variant matrices: a model's size x colour grid. Generating creates one product per missing combination, with its
own SKU and in-store EAN-13, inheriting brand and category from the model; the grid reads stock and recent sales
per cell so a buyer sees which sizes sell and which sit."""

import itertools
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.brand import ProductModel
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.variants import MatrixAxis, MatrixCell, MatrixOut, MatrixWrite
from app.services import barcodes
from app.services.inventory import _classify

POSTED = ("completed", "partially_refunded", "refunded")
SIZE_ORDER = ("XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL")


def _value_order(value: str) -> tuple[int, float, str]:
    """Letter sizes in wear order, then numeric sizes (28, 30, 42.5) by number, then everything else A-Z."""
    upper = value.upper()
    if upper in SIZE_ORDER:
        return 0, SIZE_ORDER.index(upper), ""
    number = re.match(r"^\d+(\.\d+)?", value)
    if number:
        return 1, float(number.group()), value.lower()
    return 2, 0, value.lower()


def _abbreviation(value: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", value.upper())
    if not words:
        return "X"
    if len(words) == 1:
        return words[0][:5]
    return "".join(word[:3] for word in words[:2])


def _prefix(model: ProductModel, requested: str | None) -> str:
    if requested:
        return requested.upper()
    if model.code:
        return re.sub(r"[^A-Z0-9-]", "", model.code.upper())[:16] or "VAR"
    words = re.findall(r"[A-Za-z0-9]+", model.name.upper())[:3] or ["VAR"]
    return "-".join(word[:4] for word in words)


def _key(attributes: dict[str, str]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((key, value.lower()) for key, value in attributes.items()))


def _model(db: Session, model_id: uuid.UUID) -> ProductModel:
    model = db.get(ProductModel, model_id)
    if model is None:
        raise ApiError(404, "not_found", "Model was not found.")
    return model


def matrix(db: Session, model_id: uuid.UUID, *, store_id: uuid.UUID | None = None) -> MatrixOut:
    model = _model(db, model_id)
    products = list(db.scalars(select(Product).where(Product.product_model_id == model.id).order_by(Product.sku)).all())
    ids = [product.id for product in products]
    stock: dict[uuid.UUID, dict[str, int]] = defaultdict(dict)
    sold: dict[uuid.UUID, int] = defaultdict(int)
    if ids:
        levels = (
            select(InventoryLevel.product_id, Store.code, InventoryLevel.quantity_on_hand)
            .join(Store, Store.id == InventoryLevel.store_id)
            .where(InventoryLevel.product_id.in_(ids))
        )
        if store_id is not None:
            levels = levels.where(InventoryLevel.store_id == store_id)
        for product_id, code, quantity in db.execute(levels):
            stock[product_id][code] = int(quantity)
        sales = (
            select(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(
                SaleItem.product_id.in_(ids),
                Sale.is_quote_proforma.is_(False),
                Sale.status.in_(POSTED),
                Sale.created_at >= datetime.now(UTC) - timedelta(days=90),
            )
            .group_by(SaleItem.product_id)
        )
        if store_id is not None:
            sales = sales.where(Sale.store_id == store_id)
        sold.update({product_id: int(units) for product_id, units in db.execute(sales)})

    values: dict[str, list[str]] = {}
    for product in products:
        for key, value in (product.variant_attributes or {}).items():
            bucket = values.setdefault(key, [])
            if value not in bucket:
                bucket.append(value)
    axes = [MatrixAxis(key=key, values=sorted(found, key=_value_order)) for key, found in values.items()]
    cells = [
        MatrixCell(
            attributes=product.variant_attributes or {},
            product_id=product.id,
            sku=product.sku,
            barcode=product.barcode,
            name=product.name,
            price_cents=product.price_cents,
            on_hand=sum(stock[product.id].values()),
            sold_90d=sold[product.id],
            by_store=stock[product.id],
        )
        for product in products
    ]
    return MatrixOut(
        model_id=model.id,
        model_name=model.name,
        axes=axes,
        cells=cells,
        on_hand=sum(cell.on_hand for cell in cells),
        sold_90d=sum(cell.sold_90d for cell in cells),
    )


def generate(db: Session, model_id: uuid.UUID, data: MatrixWrite, currency: str) -> MatrixOut:
    model = _model(db, model_id)
    existing = {
        _key(product.variant_attributes or {})
        for product in db.scalars(select(Product).where(Product.product_model_id == model.id))
    }
    prefix = _prefix(model, data.sku_prefix)
    prices = {value.lower(): price for value, price in data.price_by_value.items()}
    reserved: set[str] = set()
    created = skipped = 0
    for combination in itertools.product(*(axis.values for axis in data.axes)):
        attributes = {axis.key: value for axis, value in zip(data.axes, combination, strict=True)}
        if _key(attributes) in existing:
            skipped += 1
            continue
        stem = f"{prefix}-{'-'.join(_abbreviation(value) for value in combination)}"[:60]
        sku = stem
        suffix = 2
        while barcodes.code_taken(db, sku, reserved):
            sku = f"{stem}-{suffix}"
            suffix += 1
        reserved.add(sku.lower())
        price = max([data.price_cents, *(prices[value.lower()] for value in combination if value.lower() in prices)])
        product = Product(
            sku=sku,
            barcode=barcodes.in_store_ean13(db, reserved),
            name=" ".join([model.name, *combination])[:200],
            model_number=model.code,
            variant_attributes=attributes,
            price_cents=price,
            currency=currency,
            is_serialized=False,
            tax_category=data.tax_category,
        )
        _classify(db, product, model_id=model.id, category_id=None, sub_category_id=None, brand=None)
        db.add(product)
        db.flush()
        existing.add(_key(attributes))
        created += 1
    db.commit()
    result = matrix(db, model.id)
    result.created, result.skipped = created, skipped
    return result
