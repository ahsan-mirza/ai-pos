"""Read-only history for one catalog product: sales, purchasing, serial units, and the stock ledger.
Store-bound users only ever see their own branch."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.security import decrypt_value
from app.models.batch import BatchItem, PurchaseBatch
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.purchasing import GoodsReceipt, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.serial_number import SerialNumber
from app.models.store import Store
from app.models.user import User
from app.schemas.product_history import (
    CostGapRow,
    CostLayerRow,
    CostReconciliation,
    ProductCosting,
    ProductPurchaseHistory,
    ProductPurchaseRow,
    ProductSaleRow,
    ProductSalesHistory,
    ProductSerialRow,
    ProductSerials,
    StoreCostRow,
)
from app.services.cost_layers import WEIGHTED_AVERAGE, costing_method, layered_quantity
from app.services.search_terms import identifier_candidates
from app.services.settings_service import business_currency

# Sales that never left the register as revenue.
EXCLUDED_SALE_STATUSES = ("draft", "voided", "quote")


def scope_for(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only view your own store's history.")
        return principal.store_id
    return store_id


def require_product(db: Session, product_id: uuid.UUID) -> Product:
    product = db.get(Product, product_id)
    if product is None:
        raise ApiError(404, "not_found", "Product was not found.")
    return product


def _invoice(sale: Sale) -> str:
    return sale.invoice_number or sale.client_sale_id[:8].upper()


def sales_history(db: Session, product_id: uuid.UUID, *, store_id: uuid.UUID | None, limit: int) -> ProductSalesHistory:
    require_product(db, product_id)
    currency = business_currency(db)
    conditions = [SaleItem.product_id == product_id, Sale.status.not_in(EXCLUDED_SALE_STATUSES)]
    if store_id is not None:
        conditions.append(Sale.store_id == store_id)

    units, revenue, line_value, sale_count = db.execute(
        select(
            func.coalesce(func.sum(SaleItem.quantity), 0),
            func.coalesce(func.sum(SaleItem.line_total_cents), 0),
            func.coalesce(func.sum(SaleItem.unit_price_cents * SaleItem.quantity), 0),
            func.count(func.distinct(Sale.id)),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(*conditions, Sale.currency == currency)
    ).one()

    rows = db.execute(
        select(SaleItem, Sale, Store, User.full_name)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Store, Store.id == Sale.store_id)
        .outerjoin(User, User.id == Sale.cashier_id)
        .where(*conditions)
        .order_by(Sale.created_at.desc())
        .limit(limit)
    ).all()
    return ProductSalesHistory(
        currency=currency,
        units_sold=int(units),
        revenue_cents=int(revenue),
        average_selling_price_cents=round(int(line_value) / int(units)) if units else None,
        sale_count=int(sale_count),
        rows=[
            ProductSaleRow(
                sale_id=sale.id,
                sale_item_id=item.id,
                invoice=_invoice(sale),
                sold_at=sale.created_at,
                store_id=store.id,
                store_code=store.code,
                store_name=store.name,
                cashier_name=cashier_name,
                status=sale.status,  # type: ignore[arg-type]
                currency=sale.currency,
                quantity=item.quantity,
                unit_price_cents=item.unit_price_cents,
                tax_cents=item.tax_cents,
                line_total_cents=item.line_total_cents,
                cost_cents=item.cost_cents,
                cost_estimated=item.cost_estimated,
                gross_profit_cents=(
                    None if item.cost_cents is None else item.line_total_cents - item.tax_cents - item.cost_cents
                ),
            )
            for item, sale, store, cashier_name in rows
        ],
    )


def purchase_history(
    db: Session, product_id: uuid.UUID, *, store_id: uuid.UUID | None, limit: int
) -> ProductPurchaseHistory:
    """One row per goods receipt line, plus one per order line still waiting on stock."""
    require_product(db, product_id)
    scope = [PurchaseOrder.destination_store_id == store_id] if store_id is not None else []

    received = db.execute(
        select(GoodsReceiptLine, GoodsReceipt, PurchaseOrderLine, PurchaseOrder, Store)
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrderLine, PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .join(Store, Store.id == GoodsReceipt.store_id)
        .where(GoodsReceiptLine.product_id == product_id, *scope)
        .order_by(GoodsReceipt.created_at.desc())
        .limit(limit)
    ).all()
    pending = db.execute(
        select(PurchaseOrderLine, PurchaseOrder, Store)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .join(Store, Store.id == PurchaseOrder.destination_store_id)
        .where(
            PurchaseOrderLine.product_id == product_id,
            PurchaseOrderLine.quantity_received == 0,
            PurchaseOrder.status.in_(("draft", "ordered", "partially_received")),
            *scope,
        )
        .order_by(PurchaseOrder.created_at.desc())
        .limit(limit)
    ).all()

    rows = [
        ProductPurchaseRow(
            purchase_order_id=order.id,
            po_number=order.number,
            po_status=order.status,  # type: ignore[arg-type]
            goods_receipt_id=receipt.id,
            grn_number=receipt.number,
            supplier_name=order.supplier_name,
            store_id=store.id,
            store_code=store.code,
            ordered_at=order.ordered_at,
            received_at=receipt.created_at,
            unit_cost_cents=order_line.unit_cost_cents,
            quantity_ordered=order_line.quantity_ordered,
            quantity_received=line.quantity,
            total_cost_cents=order_line.unit_cost_cents * line.quantity,
        )
        for line, receipt, order_line, order, store in received
    ] + [
        ProductPurchaseRow(
            purchase_order_id=order.id,
            po_number=order.number,
            po_status=order.status,  # type: ignore[arg-type]
            goods_receipt_id=None,
            grn_number=None,
            supplier_name=order.supplier_name,
            store_id=store.id,
            store_code=store.code,
            ordered_at=order.ordered_at,
            received_at=None,
            unit_cost_cents=order_line.unit_cost_cents,
            quantity_ordered=order_line.quantity_ordered,
            quantity_received=0,
            total_cost_cents=order_line.unit_cost_cents * order_line.quantity_ordered,
        )
        for order_line, order, store in pending
    ]

    units, spend = db.execute(
        select(
            func.coalesce(func.sum(GoodsReceiptLine.quantity), 0),
            func.coalesce(func.sum(GoodsReceiptLine.quantity * PurchaseOrderLine.unit_cost_cents), 0),
        )
        .join(GoodsReceipt, GoodsReceipt.id == GoodsReceiptLine.goods_receipt_id)
        .join(PurchaseOrderLine, PurchaseOrderLine.id == GoodsReceiptLine.purchase_order_line_id)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(GoodsReceiptLine.product_id == product_id, *scope)
    ).one()
    return ProductPurchaseHistory(
        latest_unit_cost_cents=received[0][2].unit_cost_cents if received else None,
        average_unit_cost_cents=round(int(spend) / int(units)) if units else None,
        units_received=int(units),
        total_spend_cents=int(spend),
        rows=rows,
    )


def serials(
    db: Session,
    settings: Settings,
    product_id: uuid.UUID,
    *,
    store_id: uuid.UUID | None,
    status: str | None,
    query: str | None,
    limit: int,
) -> ProductSerials:
    """Values are encrypted at rest, so the portal sees the last four digits. `query` matches a full IMEI/serial
    exactly (by hash) or the last four digits."""
    require_product(db, product_id)
    conditions = [SerialNumber.product_id == product_id]
    if store_id is not None:
        conditions.append(SerialNumber.store_id == store_id)

    counts = {
        row_status: int(count)
        for row_status, count in db.execute(
            select(SerialNumber.status, func.count()).where(*conditions).group_by(SerialNumber.status)
        ).all()
    }
    if status is not None:
        conditions.append(SerialNumber.status == status)

    needle = (query or "").strip()
    hashes = identifier_candidates(needle) if len(needle) > 4 else {}
    if len(needle) > 4 and not hashes:
        return ProductSerials(total=sum(counts.values()), status_counts=counts, rows=[])
    if hashes:
        conditions.append(SerialNumber.value_hash.in_(hashes.keys()))

    units = list(db.scalars(select(SerialNumber).where(*conditions).order_by(SerialNumber.updated_at.desc())).all())
    pairs = [(unit, decrypt_value(unit.value_encrypted, settings)[-4:]) for unit in units]
    if needle and not hashes:
        pairs = [(unit, last4) for unit, last4 in pairs if last4.endswith(needle.upper())]
    pairs = pairs[:limit]

    stores = (
        {
            store.id: store
            for store in db.scalars(select(Store).where(Store.id.in_({unit.store_id for unit, _ in pairs}))).all()
        }
        if pairs
        else {}
    )
    sold: dict[uuid.UUID, Sale] = {}
    sold_ids = [unit.id for unit, _ in pairs if unit.status == "sold"]
    if sold_ids:
        for serial_id, sale in db.execute(
            select(SaleItem.serial_number_id, Sale)
            .join(Sale, Sale.id == SaleItem.sale_id)
            .where(SaleItem.serial_number_id.in_(sold_ids))
            .order_by(Sale.created_at)
        ).all():
            sold[serial_id] = sale

    return ProductSerials(
        total=sum(counts.values()),
        status_counts=counts,
        rows=[
            ProductSerialRow(
                serial_number_id=unit.id,
                kind=unit.kind,  # type: ignore[arg-type]
                last4=last4,
                status=unit.status,  # type: ignore[arg-type]
                store_id=unit.store_id,
                store_code=stores[unit.store_id].code,
                store_name=stores[unit.store_id].name,
                sold_at=sold[unit.id].created_at if unit.id in sold else None,
                sale_invoice=_invoice(sold[unit.id]) if unit.id in sold else None,
                updated_at=unit.updated_at,
            )
            for unit, last4 in pairs
        ],
    )


def _layer_value(db: Session, product_id: uuid.UUID, store_id: uuid.UUID) -> int:
    return int(
        db.scalar(
            select(func.coalesce(func.sum(BatchItem.quantity_remaining * BatchItem.purchase_cost_per_unit), 0))
            .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
            .where(
                BatchItem.product_id == product_id,
                BatchItem.store_id == store_id,
                PurchaseBatch.status != "REVERSED",
                PurchaseBatch.is_consignment.is_(False),
            )
        )
        or 0
    )


def product_costing(db: Session, product_id: uuid.UUID, *, store_id: uuid.UUID | None) -> ProductCosting:
    product = require_product(db, product_id)
    method = costing_method(db)
    currency = business_currency(db)
    scope = [InventoryLevel.store_id == store_id] if store_id is not None else []
    levels = list(
        db.execute(
            select(InventoryLevel, Store)
            .join(Store, Store.id == InventoryLevel.store_id)
            .where(InventoryLevel.product_id == product_id, *scope)
        ).all()
    )
    stores: list[StoreCostRow] = []
    on_hand = reserved = value = uncosted = average_weight = average_units = 0
    for level, store in levels:
        layered = layered_quantity(db, product_id, level.store_id)
        gap = max(0, level.quantity_on_hand - layered)
        if method == WEIGHTED_AVERAGE and level.weighted_average_cost_cents is not None:
            branch_value = level.quantity_on_hand * level.weighted_average_cost_cents
        else:
            branch_value = _layer_value(db, product_id, level.store_id)
        stores.append(
            StoreCostRow(
                store_id=store.id,
                store_code=store.code,
                on_hand=level.quantity_on_hand,
                reserved=level.quantity_reserved,
                available=level.available,
                weighted_average_cost_cents=level.weighted_average_cost_cents,
                inventory_value_cents=branch_value,
                uncosted_quantity=gap,
            )
        )
        on_hand += level.quantity_on_hand
        reserved += level.quantity_reserved
        value += branch_value
        uncosted += gap
        if level.weighted_average_cost_cents is not None and level.quantity_on_hand:
            average_weight += level.quantity_on_hand * level.weighted_average_cost_cents
            average_units += level.quantity_on_hand
    layer_rows = db.execute(
        select(BatchItem, PurchaseBatch)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(BatchItem.product_id == product_id, *([BatchItem.store_id == store_id] if store_id else []))
        .order_by(BatchItem.created_at, BatchItem.id)
    ).all()
    revenue, cogs = db.execute(
        select(
            func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0),
            func.coalesce(func.sum(SaleItem.cost_cents), 0),
        )
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            SaleItem.product_id == product_id,
            SaleItem.cost_cents.is_not(None),
            Sale.status.not_in(EXCLUDED_SALE_STATUSES),
            Sale.currency == currency,
            *([Sale.store_id == store_id] if store_id else []),
        )
    ).one()
    return ProductCosting(
        method=method,
        currency=currency,
        default_cost_cents=product.default_cost_cents,
        last_purchase_cost_cents=product.last_purchase_cost_cents,
        weighted_average_cost_cents=round(average_weight / average_units) if average_units else None,
        on_hand=on_hand,
        reserved=reserved,
        available=on_hand - reserved,
        inventory_value_cents=value,
        uncosted_quantity=uncosted,
        realized_revenue_cents=int(revenue),
        realized_cogs_cents=int(cogs),
        realized_profit_cents=int(revenue) - int(cogs),
        layers=[
            CostLayerRow(
                batch_item_id=item.id,
                batch_id=batch.id,
                batch_number=batch.batch_number,
                goods_receipt_id=batch.goods_receipt_id,
                receipt_date=item.created_at,
                original_quantity=item.quantity_imported,
                remaining_quantity=item.quantity_remaining,
                unit_cost_cents=item.purchase_cost_per_unit,
                remaining_value_cents=item.quantity_remaining * item.purchase_cost_per_unit,
                consumed_quantity=item.quantity_imported - item.quantity_remaining,
                source=(
                    "purchase"
                    if batch.goods_receipt_id is not None
                    else "adjustment"
                    if batch.import_source == "ADJUST"
                    else "import"
                ),
            )
            for item, batch in layer_rows
            if batch.status != "REVERSED"
        ],
        stores=stores,
    )


def cost_reconciliation(db: Session, *, store_id: uuid.UUID | None) -> CostReconciliation:
    """Quantities on hand with no remaining cost layer. No opening cost is invented for them."""
    query = (
        select(InventoryLevel, Product, Store)
        .join(Product, Product.id == InventoryLevel.product_id)
        .join(Store, Store.id == InventoryLevel.store_id)
        .where(InventoryLevel.quantity_on_hand > 0)
    )
    if store_id is not None:
        query = query.where(InventoryLevel.store_id == store_id)
    rows: list[CostGapRow] = []
    for level, product, store in db.execute(query).all():
        layered = layered_quantity(db, product.id, level.store_id)
        gap = level.quantity_on_hand - layered
        if gap == 0:
            continue
        rows.append(
            CostGapRow(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                store_id=store.id,
                store_code=store.code,
                on_hand=level.quantity_on_hand,
                layered_quantity=layered,
                uncosted_quantity=gap,
            )
        )
    rows.sort(key=lambda row: (-row.uncosted_quantity, row.sku))
    return CostReconciliation(method=costing_method(db), rows=rows)
