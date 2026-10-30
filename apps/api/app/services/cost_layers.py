"""Immutable receipt cost layers and the company costing method.

A goods receipt opens a new layer at the price paid. It never rewrites an older layer.
FIFO sales consume the oldest layer. Weighted average snapshots the branch average onto the sale
and leaves that snapshot alone when a later receipt changes the average.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale_item import SaleItem
from app.services import audit, weighed
from app.services.settings_service import load_settings

FIFO = "FIFO"
WEIGHTED_AVERAGE = "WEIGHTED_AVERAGE"
METHODS = frozenset({FIFO, WEIGHTED_AVERAGE})
ADJUST_SOURCE = "ADJUST"


def costing_method(db: Session) -> str:
    method = load_settings(db).inventory_costing
    return method if method in METHODS else FIFO


def _posted_cost(db: Session) -> bool:
    return db.scalar(select(SaleItem.id).where(SaleItem.cost_cents.is_not(None)).limit(1)) is not None


def set_costing_method(
    db: Session,
    method: str,
    *,
    user_id: uuid.UUID | None,
    reason: str,
    convert: bool,
) -> str:
    """Switch the method used for sales posted after this call. Posted sale costs are not rewritten."""
    if method not in METHODS:
        raise ApiError(422, "validation_error", "Costing method must be FIFO or weighted average.")
    cleaned = reason.strip()
    if len(cleaned) < 3:
        raise ApiError(422, "reason_required", "A reason of at least 3 characters is required.")
    row = load_settings(db)
    previous = row.inventory_costing if row.inventory_costing in METHODS else FIFO
    if method == previous:
        return previous
    if _posted_cost(db) and not convert:
        raise ApiError(
            409,
            "costing_method_locked",
            "Sales already carry a cost. Convert the method with a recorded reason; posted costs stay as they are.",
        )
    row.inventory_costing = method
    audit.record(
        db,
        action_type="UPDATE",
        action="inventory.costing_method",
        target_entity="BusinessSettings",
        target_entity_id=row.id,
        user_id=user_id,
        client_device="web",
        old_values={"inventory_costing": previous},
        new_values={"inventory_costing": method},
        details={"reason": cleaned, "historical_costs": "unchanged"},
    )
    db.commit()
    return method


def _average(previous_qty: int, previous: int | None, received: int, unit_cost: int) -> int | None:
    """Perpetual average. Unknown cost already on hand is left unknown instead of being assigned this price."""
    if previous_qty <= 0:
        return unit_cost
    if previous is None:
        return None
    total = previous_qty * previous + received * unit_cost
    return (total + (previous_qty + received) // 2) // (previous_qty + received)


def _blend(quantity: int, unit_cost_cents: int, landed_cost_cents: int, scale: int) -> int:
    """Fold a one-off landed amount into the unit cost so the layer stores a single immutable price."""
    total = weighed.amount(quantity, unit_cost_cents, scale) + landed_cost_cents
    if quantity <= 0:
        return unit_cost_cents
    if scale == 1:
        return (total + quantity // 2) // quantity
    return (total * scale + quantity // 2) // quantity


def _stamp(row: PurchaseBatch | BatchItem, when: datetime | None) -> None:
    if when is not None:
        row.created_at = when


def record_adjustment_layer(
    db: Session,
    *,
    product: Product,
    store_id: uuid.UUID,
    quantity: int,
    unit_cost_cents: int,
    landed_cost_cents: int,
    user_id: uuid.UUID,
    currency: str,
    adjustment_id: uuid.UUID,
    note: str,
    lot_number: str | None = None,
    expiry_date: date | None = None,
    supplier_reference: str | None = None,
    receipt_date: date | None = None,
) -> BatchItem:
    """Open one cost layer for a manual addition. It is not a supplier receipt and is not billed."""
    scale = weighed.scale_of(product)
    unit = _blend(quantity, unit_cost_cents, landed_cost_cents, scale)
    when = datetime.combine(receipt_date, time(12), tzinfo=UTC) if receipt_date is not None else None
    detail = [note]
    if supplier_reference:
        detail.append(f"Ref {supplier_reference}")
    if landed_cost_cents:
        detail.append(f"Landed {landed_cost_cents}")
    batch = PurchaseBatch(
        batch_number=(lot_number or f"ADJ-{adjustment_id.hex[:8].upper()}")[:32],
        store_id=store_id,
        goods_receipt_id=None,
        import_source=ADJUST_SOURCE,
        file_name=str(adjustment_id),
        total_cost_amount=weighed.amount(quantity, unit, scale),
        total_items_count=quantity,
        currency=currency,
        status="ACTIVE",
        notes=" · ".join(detail)[:1000],
        created_by_id=user_id,
    )
    _stamp(batch, when)
    db.add(batch)
    db.flush()
    item = BatchItem(
        batch_id=batch.id,
        product_id=product.id,
        store_id=store_id,
        quantity_imported=quantity,
        quantity_remaining=quantity,
        purchase_cost_per_unit=unit,
        selling_price_per_unit=product.price_cents,
        expiry_date=expiry_date,
    )
    _stamp(item, when)
    db.add(item)
    product.last_purchase_cost_cents = unit
    if product.default_cost_cents is None:
        product.default_cost_cents = unit
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store_id)
    )
    if level is not None:
        level.weighted_average_cost_cents = _average(
            level.quantity_on_hand - quantity, level.weighted_average_cost_cents, quantity, unit
        )
    db.flush()
    return item


def record_receipt_layer(
    db: Session,
    *,
    product: Product,
    store_id: uuid.UUID,
    quantity: int,
    unit_cost_cents: int,
    goods_receipt_id: uuid.UUID,
    user_id: uuid.UUID,
    supplier_id: uuid.UUID | None,
    currency: str,
    note: str,
    batch_number: str | None = None,
) -> BatchItem:
    """Open one cost layer for units just received. The caller has already increased on-hand."""
    batch = PurchaseBatch(
        batch_number=(batch_number or f"R-{uuid.uuid4().hex[:10].upper()}")[:32],
        supplier_id=supplier_id,
        store_id=store_id,
        goods_receipt_id=goods_receipt_id,
        import_source="MANUAL",
        total_cost_amount=quantity * unit_cost_cents,
        total_items_count=quantity,
        currency=currency,
        status="ACTIVE",
        notes=note[:1000],
        created_by_id=user_id,
    )
    db.add(batch)
    db.flush()
    item = BatchItem(
        batch_id=batch.id,
        product_id=product.id,
        store_id=store_id,
        quantity_imported=quantity,
        quantity_remaining=quantity,
        purchase_cost_per_unit=unit_cost_cents,
        selling_price_per_unit=product.price_cents,
    )
    db.add(item)
    product.last_purchase_cost_cents = unit_cost_cents
    if product.default_cost_cents is None:
        product.default_cost_cents = unit_cost_cents
    level = db.scalar(
        select(InventoryLevel).where(InventoryLevel.product_id == product.id, InventoryLevel.store_id == store_id)
    )
    if level is not None:
        previous_qty = level.quantity_on_hand - quantity
        level.weighted_average_cost_cents = _average(
            previous_qty, level.weighted_average_cost_cents, quantity, unit_cost_cents
        )
    db.flush()
    return item


def layered_quantity(db: Session, product_id: uuid.UUID, store_id: uuid.UUID | None) -> int:
    query = (
        select(func.coalesce(func.sum(BatchItem.quantity_remaining), 0))
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(
            BatchItem.product_id == product_id,
            PurchaseBatch.status != "REVERSED",
            PurchaseBatch.is_consignment.is_(False),
        )
    )
    if store_id is not None:
        query = query.where(BatchItem.store_id == store_id)
    return int(db.scalar(query) or 0)
