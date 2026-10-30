"""Cost of goods sold. Units drawn from purchase batches carry their FIFO cost (batch_ledger writes the
allocations); units with no batch (opening balances, goods receipts, transfers in) are costed at the most recent
goods-receipt cost and the line is flagged cost_estimated."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.batch import BatchAllocation, BatchItem
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrderLine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.services import batch_ledger, weighed
from app.services.cost_layers import WEIGHTED_AVERAGE, costing_method


def fallback_unit_cost(db: Session, product_id: uuid.UUID) -> int | None:
    received = db.scalar(
        select(PurchaseOrderLine.unit_cost_cents)
        .join(GoodsReceiptLine, GoodsReceiptLine.purchase_order_line_id == PurchaseOrderLine.id)
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .where(GoodsReceiptLine.product_id == product_id, PurchaseOrderLine.unit_cost_cents > 0)
        .order_by(GoodsReceipt.created_at.desc())
        .limit(1)
    )
    if received is not None:
        return int(received)
    batch = db.scalar(
        select(BatchItem.purchase_cost_per_unit)
        .where(BatchItem.product_id == product_id)
        .order_by(BatchItem.created_at.desc())
        .limit(1)
    )
    return int(batch) if batch is not None else None


def next_unit_cost(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> tuple[int | None, bool]:
    """Cost of the next unit to leave this branch: the first open batch layer in draw order (FIFO, or FEFO when that
    module is on), else the fallback (estimated)."""
    layers = batch_ledger.open_items(db, product_id, store_id)
    if layers:
        return int(layers[0].purchase_cost_per_unit), False
    return fallback_unit_cost(db, product_id), True


def cost_sale(db: Session, sale_id: uuid.UUID) -> None:
    """Writes cost_cents on every line of a recorded sale. Call after batch_ledger.link_sale."""
    items = list(db.scalars(select(SaleItem).where(SaleItem.sale_id == sale_id)).all())
    if not items:
        return
    drawn = {
        row[0]: (int(row[1] or 0), int(row[2] or 0))
        for row in db.execute(
            select(
                BatchAllocation.sale_item_id,
                func.sum(BatchAllocation.quantity),
                func.sum(BatchAllocation.quantity * BatchAllocation.unit_cost_cents),
            )
            .where(BatchAllocation.sale_item_id.in_([item.id for item in items]))
            .group_by(BatchAllocation.sale_item_id)
        ).all()
    }
    weighed_ids = set(
        db.scalars(
            select(Product.id).where(
                Product.id.in_({item.product_id for item in items}), Product.sold_by_weight.is_(True)
            )
        ).all()
    )
    average_cost = costing_method(db) == WEIGHTED_AVERAGE
    sale = db.get(Sale, sale_id) if average_cost else None
    averages: dict[uuid.UUID, int | None] = {}
    fallbacks: dict[uuid.UUID, int | None] = {}
    for item in items:
        scale = weighed.GRAMS_PER_KG if item.product_id in weighed_ids else 1
        if average_cost and sale is not None:
            if item.product_id not in averages:
                averages[item.product_id] = db.scalar(
                    select(InventoryLevel.weighted_average_cost_cents).where(
                        InventoryLevel.product_id == item.product_id,
                        InventoryLevel.store_id == sale.store_id,
                    )
                )
            average = averages[item.product_id]
            if average is not None:
                item.cost_cents = weighed.amount(item.quantity, int(average), scale)
                item.cost_estimated = False
                continue
        quantity, cost = drawn.get(item.id, (0, 0))
        # Weighed goods: allocations are grams and costs per kilogram.
        cost = weighed.amount(1, cost, scale)
        missing = max(0, item.quantity - quantity)
        estimated = False
        if missing:
            if item.product_id not in fallbacks:
                fallbacks[item.product_id] = fallback_unit_cost(db, item.product_id)
            unit = fallbacks[item.product_id]
            if unit is None:
                item.cost_cents = cost if quantity else None
                item.cost_estimated = True
                continue
            cost += weighed.amount(missing, unit, scale)
            estimated = True
        item.cost_cents = cost
        item.cost_estimated = estimated
    db.flush()
