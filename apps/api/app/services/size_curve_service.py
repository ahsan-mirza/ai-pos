"""Size-curve sell-through. Sell-through is sold / (sold + still on hand). A broken run is a size that is
out at one branch while that branch still holds other sizes and another branch can spare one."""

import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.inventory import InventoryLevel, StockMovement
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.size_curve import BrokenRun, SizeCell, SizeCurveReport

POSTED = ("completed", "partially_refunded", "refunded")
INBOUND = ("PURCHASE_IN", "TRANSFER_IN")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime(start.year, start.month, start.day, tzinfo=UTC),
        datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1),
    )


def _ordered_keys(attributes: dict[str, str]) -> list[str]:
    """Size and colour first when those axes exist; otherwise the attributes in stored order."""
    preferred = ("size", "color", "colour")
    ordered = [key for key in preferred if key in attributes]
    ordered.extend(key for key in attributes if key not in ordered)
    return ordered


def _size_color(attributes: dict[str, str]) -> tuple[str, str | None]:
    ordered = _ordered_keys(attributes)
    size = attributes[ordered[0]] if ordered else "—"
    color = attributes[ordered[1]] if len(ordered) > 1 else None
    return size, color


def _bps(part: int, whole: int) -> int:
    if whole <= 0:
        return 0
    return (part * 10_000 + whole // 2) // whole


def report(
    db: Session,
    *,
    model_id: uuid.UUID | None,
    category_id: uuid.UUID | None,
    season: str | None,
    store_id: uuid.UUID | None,
    start: date,
    end: date,
) -> SizeCurveReport:
    if model_id is None and category_id is None and not season:
        raise ApiError(422, "invalid_request", "Choose a model, a category or a season.")
    statement = select(Product).where(Product.product_model_id.is_not(None))
    if model_id is not None:
        statement = statement.where(Product.product_model_id == model_id)
    if category_id is not None:
        statement = statement.where(Product.category_id == category_id)
    if season:
        statement = statement.where(Product.season == season.strip().upper())
    products = list(db.scalars(statement))
    if not products:
        return SizeCurveReport(cells=[], broken_runs=[])
    ids = [product.id for product in products]
    since, until = _bounds(start, end)

    sold_rows = db.execute(
        select(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            SaleItem.product_id.in_(ids),
            Sale.status.in_(POSTED),
            Sale.is_quote_proforma.is_(False),
            Sale.created_at >= since,
            Sale.created_at < until,
            *([Sale.store_id == store_id] if store_id is not None else []),
        )
        .group_by(SaleItem.product_id)
    ).all()
    sold = {product_id: int(quantity) for product_id, quantity in sold_rows}

    received_rows = db.execute(
        select(StockMovement.product_id, func.coalesce(func.sum(StockMovement.quantity), 0))
        .where(
            StockMovement.product_id.in_(ids),
            StockMovement.movement_type.in_(INBOUND),
            StockMovement.created_at >= since,
            StockMovement.created_at < until,
            *([StockMovement.store_id == store_id] if store_id is not None else []),
        )
        .group_by(StockMovement.product_id)
    ).all()
    received = {product_id: int(quantity) for product_id, quantity in received_rows}

    on_hand_rows = db.execute(
        select(InventoryLevel.product_id, func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0))
        .where(
            InventoryLevel.product_id.in_(ids),
            *([InventoryLevel.store_id == store_id] if store_id is not None else []),
        )
        .group_by(InventoryLevel.product_id)
    ).all()
    on_hand = {product_id: int(quantity) for product_id, quantity in on_hand_rows}

    total_sold = sum(sold.values())
    total_stock = sum(on_hand.values())
    cells = []
    for product in products:
        size, color = _size_color(product.variant_attributes or {})
        sold_qty = sold.get(product.id, 0)
        stock_qty = on_hand.get(product.id, 0)
        cells.append(
            SizeCell(
                product_id=product.id,
                sku=product.sku,
                attributes=product.variant_attributes or {},
                size=size,
                color=color,
                received=received.get(product.id, 0),
                sold=sold_qty,
                on_hand=stock_qty,
                sell_through_bps=_bps(sold_qty, sold_qty + stock_qty),
                sales_share_bps=_bps(sold_qty, total_sold),
                stock_share_bps=_bps(stock_qty, total_stock),
            )
        )
    cells.sort(key=lambda cell: (cell.size, cell.color or ""))
    return SizeCurveReport(cells=cells, broken_runs=_broken(db, products, store_id))


def _broken(db: Session, products: list[Product], store_id: uuid.UUID | None) -> list[BrokenRun]:
    ids = [product.id for product in products]
    levels = list(
        db.scalars(
            select(InventoryLevel).where(
                InventoryLevel.product_id.in_(ids),
                *([InventoryLevel.store_id == store_id] if store_id is not None else []),
            )
        )
    )
    by_product = {product.id: product for product in products}
    stores = {row.id: row for row in db.scalars(select(Store))}
    # store -> size -> (on_hand, product)
    grid: dict[uuid.UUID, dict[str, tuple[int, Product]]] = {}
    for level in levels:
        product = by_product[level.product_id]
        size, _color = _size_color(product.variant_attributes or {})
        grid.setdefault(level.store_id, {})
        current, _ = grid[level.store_id].get(size, (0, product))
        grid[level.store_id][size] = (current + level.quantity_on_hand, product)
    # Every store's stock of a size, so a broken branch can name a donor.
    everywhere = list(db.scalars(select(InventoryLevel).where(InventoryLevel.product_id.in_(ids))))
    donors: dict[str, list[tuple[int, uuid.UUID]]] = {}
    for level in everywhere:
        product = by_product.get(level.product_id)
        if product is None:
            continue
        size, _color = _size_color(product.variant_attributes or {})
        spare = level.quantity_on_hand - level.quantity_reserved
        if spare > 0:
            donors.setdefault(size, []).append((spare, level.store_id))
    broken: list[BrokenRun] = []
    for branch_id, sizes in grid.items():
        if not any(stock > 0 for stock, _ in sizes.values()):
            continue
        for size, (stock, product) in sizes.items():
            if stock > 0:
                continue
            options = [item for item in donors.get(size, []) if item[1] != branch_id]
            donor = max(options, default=None)
            if donor is None:
                continue
            _color = _size_color(product.variant_attributes or {})[1]
            broken.append(
                BrokenRun(
                    store_id=branch_id,
                    store_name=stores[branch_id].name if branch_id in stores else "",
                    size=size,
                    color=_color,
                    suggest_from_store_id=donor[1],
                    suggest_from_name=stores[donor[1]].name if donor[1] in stores else None,
                    quantity=1,
                )
            )
    return broken


def sales_shares(db: Session, product_ids: list[uuid.UUID], days: int = 90) -> dict[uuid.UUID, int]:
    """Each product's share of units sold, in basis points. Equal shares when nothing sold."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = db.execute(
        select(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            SaleItem.product_id.in_(product_ids),
            Sale.status.in_(POSTED),
            Sale.is_quote_proforma.is_(False),
            Sale.created_at >= since,
        )
        .group_by(SaleItem.product_id)
    ).all()
    sold = {product_id: int(quantity) for product_id, quantity in rows}
    total = sum(sold.values())
    if total <= 0:
        share = 10_000 // len(product_ids)
        return {product_id: share for product_id in product_ids}
    return {product_id: _bps(sold.get(product_id, 0), total) for product_id in product_ids}
