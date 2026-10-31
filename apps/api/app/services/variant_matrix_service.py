"""Variant matrices: a model's size x colour grid. Generating creates one product per missing combination, with its
own SKU and in-store EAN-13, inheriting brand and category from the model; the grid reads stock and recent sales
per cell so a buyer sees which sizes sell and which sit."""

import itertools
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ApiError, field_conflict
from app.models.batch import BatchItem, PurchaseBatch
from app.models.brand import ProductModel
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.variants import (
    MatrixAxis,
    MatrixBulk,
    MatrixBulkResult,
    MatrixCell,
    MatrixOut,
    MatrixPreview,
    MatrixVariantDraft,
    MatrixWrite,
)
from app.services import barcodes
from app.services.inventory import _classify, _store, level_for, move_stock
from app.services.variant_keys import apply_signature, resolved_price, rules_from_values

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


def _model(db: Session, model_id: uuid.UUID, *, lock: bool = False) -> ProductModel:
    statement = select(ProductModel).where(ProductModel.id == model_id)
    if lock and db.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update()
    model = db.scalar(statement)
    if model is None:
        raise ApiError(404, "not_found", "Model was not found.")
    return model


def _latest_costs(db: Session, ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    if not ids:
        return {}
    ranked = (
        select(
            BatchItem.product_id.label("product_id"),
            BatchItem.purchase_cost_per_unit.label("cost"),
            func.row_number().over(partition_by=BatchItem.product_id, order_by=BatchItem.created_at.desc()).label("rn"),
        )
        .where(BatchItem.product_id.in_(ids))
        .subquery()
    )
    return {
        product_id: int(cost)
        for product_id, cost in db.execute(select(ranked.c.product_id, ranked.c.cost).where(ranked.c.rn == 1))
    }


def _combinations(data: MatrixWrite) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for combination in itertools.product(*(axis.values for axis in data.axes)):
        rows.append({axis.key: value for axis, value in zip(data.axes, combination, strict=True)})
    return rows


def _requested(data: MatrixWrite) -> list[tuple[dict[str, str], MatrixVariantDraft | None]]:
    """Explicit drafts when the caller chose combinations; otherwise the full grid."""
    if data.variants is not None:
        return [(dict(draft.attributes), draft) for draft in data.variants]
    return [(attributes, None) for attributes in _combinations(data)]


def _clash(db: Session, code: str, reserved: set[str], *, ignore: uuid.UUID | None = None) -> bool:
    lowered = code.lower()
    if lowered in reserved:
        return True
    statement = select(Product.id).where(
        or_(func.lower(Product.sku) == lowered, func.lower(Product.barcode) == lowered)
    )
    if ignore is not None:
        statement = statement.where(Product.id != ignore)
    return db.scalar(statement) is not None


def _opening_batch(
    db: Session,
    product: Product,
    *,
    store_id: uuid.UUID,
    user_id: uuid.UUID,
    quantity: int,
    cost_cents: int,
) -> None:
    """Records this variant's own cost. A positive quantity is also the opening receipt."""
    batch = PurchaseBatch(
        batch_number=f"OPEN-{uuid.uuid4().hex[:12]}".upper(),
        store_id=store_id,
        import_source="MANUAL",
        total_cost_amount=quantity * cost_cents,
        total_items_count=quantity,
        currency=product.currency,
        status="ACTIVE",
        notes="Opening stock",
        created_by_id=user_id,
    )
    db.add(batch)
    db.flush()
    db.add(
        BatchItem(
            batch_id=batch.id,
            position=0,
            product_id=product.id,
            store_id=store_id,
            quantity_imported=quantity,
            quantity_remaining=quantity,
            purchase_cost_per_unit=cost_cents,
            selling_price_per_unit=product.price_cents,
            imported_serials=[],
        )
    )
    db.flush()
    if quantity > 0:
        move_stock(
            db,
            product_id=product.id,
            store_id=store_id,
            quantity=quantity,
            movement_type="PURCHASE_IN",
            reference_type="purchase_batch",
            reference_id=batch.id,
            user_id=user_id,
            note=f"{batch.batch_number} · opening stock",
        )


def _stock_new(
    db: Session,
    product: Product,
    draft: MatrixVariantDraft | None,
    *,
    store_id: uuid.UUID | None,
    user_id: uuid.UUID | None,
) -> None:
    if draft is None or store_id is None:
        return
    quantity = draft.opening_quantity or 0
    reorder = draft.min_reorder_level
    if reorder:
        level_for(db, product.id, store_id).min_reorder_level = reorder
    if draft.cost_cents is not None and user_id is not None:
        _opening_batch(
            db,
            product,
            store_id=store_id,
            user_id=user_id,
            quantity=quantity,
            cost_cents=draft.cost_cents,
        )
        return
    if quantity > 0:
        move_stock(
            db,
            product_id=product.id,
            store_id=store_id,
            quantity=quantity,
            movement_type="AUDIT_ADJUSTMENT",
            reference_type="opening_balance",
            reference_id=product.id,
            user_id=user_id,
            note="Opening stock",
        )


def _touch(
    db: Session,
    product: Product,
    draft: MatrixVariantDraft,
    model: ProductModel,
    *,
    user_id: uuid.UUID | None,
) -> None:
    """Updates a variant that already exists. Opening stock is not applied again."""
    if product.product_model_id not in (None, model.id):
        raise ApiError(422, "model_mismatch", "That product belongs to another model.")
    if product.product_model_id != model.id or (product.variant_attributes or {}) != draft.attributes:
        product.variant_attributes = draft.attributes
        _classify(db, product, model_id=model.id, category_id=None, sub_category_id=None, brand=None)
        apply_signature(product)
    if draft.sku and draft.sku != product.sku:
        if _clash(db, draft.sku, set(), ignore=product.id):
            raise field_conflict("SKU is already in use.", sku="SKU is already in use.")
        product.sku = draft.sku
    if draft.barcode and draft.barcode != product.barcode:
        if _clash(db, draft.barcode, set(), ignore=product.id):
            raise field_conflict("Barcode is already in use.", barcode="Barcode is already in use.")
        product.barcode = draft.barcode
    if draft.is_active is not None and draft.is_active != product.is_active:
        product.is_active = draft.is_active
    if draft.price_cents is not None and draft.price_cents != product.price_cents:
        from app.services import markdown_service

        markdown_service.record(db, product, draft.price_cents, "BULK", user_id=user_id)
        product.price_cents = draft.price_cents
        product.price_source = "override"


def matrix(db: Session, model_id: uuid.UUID, *, store_id: uuid.UUID | None = None) -> MatrixOut:
    model = _model(db, model_id)
    products = list(db.scalars(select(Product).where(Product.product_model_id == model.id).order_by(Product.sku)).all())
    ids = [product.id for product in products]
    costs = _latest_costs(db, ids)
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
            price_source=product.price_source,
            is_active=product.is_active,
            cost_cents=costs.get(product.id),
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


def preview(db: Session, model_id: uuid.UUID, data: MatrixWrite) -> MatrixPreview:
    model = _model(db, model_id)
    products = list(db.scalars(select(Product).where(Product.product_model_id == model.id)))
    existing_keys = {_key(product.variant_attributes or {}) for product in products}
    inactive = {_key(product.variant_attributes or {}) for product in products if not product.is_active}
    seen: set[tuple[tuple[str, str], ...]] = set()
    creating = existing = duplicates = 0
    for attributes, _draft in _requested(data):
        key = _key(attributes)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if key in existing_keys:
            existing += 1
        else:
            creating += 1
    possible = existing + creating
    return MatrixPreview(
        possible=possible,
        existing=existing,
        creating=creating,
        inactive=sum(1 for key in seen if key in inactive),
        duplicates=duplicates,
        over_limit=possible > 400,
    )


def generate(
    db: Session,
    model_id: uuid.UUID,
    data: MatrixWrite,
    currency: str,
    *,
    user_id: uuid.UUID | None = None,
) -> MatrixOut:
    model = _model(db, model_id, lock=True)
    from app.services.inventory import reject_foreign_specs

    sub = model.sub_category
    reject_foreign_specs(
        db,
        dict(data.specifications),
        category=sub.category.name,
        sub_category=sub.name,
        product_name=model.name,
    )
    if data.opening_store_id is not None:
        _store(db, data.opening_store_id)
    products = list(db.scalars(select(Product).where(Product.product_model_id == model.id)))
    by_key = {_key(product.variant_attributes or {}): product for product in products}
    by_id = {product.id: product for product in products}
    # Remember the prices for new cells. An existing variant's own price, SKU, barcode, and stock stay unless a
    # draft names that combination and sets a new value. Opening stock is applied only when the row is created.
    model.default_price_cents = data.price_cents
    model.price_rules = rules_from_values([(axis.key, axis.values) for axis in data.axes], data.price_by_value)
    prefix = _prefix(model, data.sku_prefix)
    reserved: set[str] = set()
    created = skipped = 0
    for attributes, draft in _requested(data):
        key = _key(attributes)
        current = by_id.get(draft.product_id) if draft and draft.product_id else None
        if current is None:
            current = by_key.get(key)
        if current is not None:
            owner = by_key.get(key)
            if owner is not None and owner.id != current.id:
                raise field_conflict(
                    "This combination already exists.",
                    variant_attributes="This combination already exists.",
                )
            if draft is not None:
                _touch(db, current, draft, model, user_id=user_id)
                by_key[_key(current.variant_attributes or {})] = current
            skipped += 1
            continue
        ordered = [attributes[axis.key] for axis in data.axes if axis.key in attributes]
        if draft and draft.sku:
            if _clash(db, draft.sku, reserved):
                raise field_conflict("SKU is already in use.", sku="SKU is already in use.")
            sku = draft.sku
        else:
            stem = f"{prefix}-{'-'.join(_abbreviation(value) for value in ordered)}"[:60]
            sku = stem
            suffix = 2
            while _clash(db, sku, reserved):
                sku = f"{stem}-{suffix}"
                suffix += 1
        reserved.add(sku.lower())
        if draft and draft.barcode:
            if _clash(db, draft.barcode, reserved):
                raise field_conflict("Barcode is already in use.", barcode="Barcode is already in use.")
            barcode = draft.barcode
        else:
            barcode = barcodes.in_store_ean13(db, reserved)
        reserved.add(barcode.lower())
        price, source = resolved_price(data.price_cents, model.price_rules, attributes)
        if draft and draft.price_cents is not None:
            price, source = draft.price_cents, "override"
        product = Product(
            sku=sku,
            barcode=barcode,
            name=" ".join([model.name, *ordered])[:200],
            model_number=model.code,
            variant_attributes=attributes,
            specifications=dict(data.specifications),
            price_cents=price,
            price_source=source,
            currency=currency,
            is_serialized=False,
            is_active=True if draft is None or draft.is_active is None else draft.is_active,
            tax_category=data.tax_category,
            price_includes_tax=data.price_includes_tax,
        )
        _classify(db, product, model_id=model.id, category_id=None, sub_category_id=None, brand=None)
        try:
            with db.begin_nested():
                db.add(product)
                db.flush()
        except IntegrityError:
            skipped += 1
            continue
        _stock_new(db, product, draft, store_id=data.opening_store_id, user_id=user_id)
        by_key[key] = product
        by_id[product.id] = product
        created += 1
    db.commit()
    result = matrix(db, model.id)
    result.created, result.skipped = created, skipped
    return result


def bulk(db: Session, model_id: uuid.UUID, data: MatrixBulk, *, user_id: uuid.UUID | None) -> MatrixBulkResult:
    model = _model(db, model_id)
    products = list(
        db.scalars(select(Product).where(Product.product_model_id == model.id, Product.id.in_(data.product_ids)))
    )
    found = {product.id for product in products}
    skipped = [product_id for product_id in data.product_ids if product_id not in found]
    reserved: set[str] = set()
    updated = 0
    from app.services import markdown_service

    for product in products:
        changed = False
        if data.price_cents is not None and not (data.only_unset and product.price_source == "override"):
            if data.price_cents != product.price_cents:
                markdown_service.record(db, product, data.price_cents, "BULK", user_id=user_id)
                product.price_cents = data.price_cents
            product.price_source = "override"
            changed = True
        if data.is_active is not None and data.is_active != product.is_active:
            product.is_active = data.is_active
            changed = True
        if data.assign_missing_barcodes and not (product.barcode or "").strip():
            product.barcode = barcodes.in_store_ean13(db, reserved)
            reserved.add(product.barcode.lower())
            changed = True
        if data.min_reorder_level is not None and data.store_id is not None:
            level = level_for(db, product.id, data.store_id)
            untouched = data.only_unset and level.min_reorder_level not in (0, data.min_reorder_level)
            if not untouched and level.min_reorder_level != data.min_reorder_level:
                level.min_reorder_level = data.min_reorder_level
                changed = True
        if changed:
            updated += 1
    db.commit()
    return MatrixBulkResult(updated=updated, skipped=skipped)
