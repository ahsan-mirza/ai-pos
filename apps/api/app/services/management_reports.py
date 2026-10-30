"""Management reports: P&L by branch and month, FIFO inventory valuation, slow and dead stock, sales by staff.

Revenue is net of VAT and promotion discounts. Cost of goods is the FIFO cost written on each sale line, less the
cost of units customers returned. Operating expenses are expenses (with VAT that could not be recovered),
supplier bill lines that are not stock, and stock written off at cost."""

from __future__ import annotations

import csv
import io
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.models.batch import BatchAllocation, BatchItem, PurchaseBatch
from app.models.inventory import InventoryLevel, StockMovement
from app.models.payables import SupplierBill, SupplierBillLine
from app.models.product import Product
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.user import User
from app.schemas.management import (
    AgedStockReport,
    AgedStockRow,
    DiscountReasonTotal,
    DiscountReport,
    DiscountRow,
    PnlReport,
    PnlRow,
    StaffSalesReport,
    StaffSalesRow,
    ValuationGroup,
    ValuationReport,
    ValuationRow,
)
from app.services import consignment_service, costing, expense_service, margin_service, sales_velocity, weighed
from app.services.cost_layers import costing_method
from app.services.settings_service import cached_settings, pos_policy
from app.services.tax import div_half_up
from app.services.tax import policy as tax_policy

POSTED = ("completed", "partially_refunded", "refunded")
SHRINK_REFERENCES = ("manual_adjustment", "stock_count")
SHRINK_TYPES = ("DAMAGE_SHRINKAGE", "AUDIT_ADJUSTMENT")


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    if end < start or (end - start).days > 400:
        raise ApiError(422, "validation_error", "Choose a period of at most 400 days that ends after it starts.")
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _month(value: datetime | date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _margin(profit: int, revenue: int) -> int:
    return round(profit * 10_000 / revenue) if revenue else 0


class _Costs:
    """Latest purchase cost per product, for units no purchase batch covers."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.cache: dict[uuid.UUID, int | None] = {}

    def __call__(self, product_id: uuid.UUID) -> int | None:
        if product_id not in self.cache:
            self.cache[product_id] = costing.fallback_unit_cost(self.db, product_id)
        return self.cache[product_id]


# --- P&L ---------------------------------------------------------------------------------------------------


def _blank(month: str, store_id: uuid.UUID | None, store_code: str) -> dict:
    return {
        "month": month,
        "store_id": store_id,
        "store_code": store_code,
        "net_sales_cents": 0,
        "returns_cents": 0,
        "cogs_cents": 0,
        "expenses": defaultdict(int),
        "other_purchases_cents": 0,
        "shrinkage_cents": 0,
    }


def _finish(raw: dict) -> PnlRow:
    revenue = raw["net_sales_cents"] - raw["returns_cents"]
    gross = revenue - raw["cogs_cents"]
    operating = sum(raw["expenses"].values()) + raw["other_purchases_cents"] + raw["shrinkage_cents"]
    return PnlRow(
        month=raw["month"],
        store_id=raw["store_id"],
        store_code=raw["store_code"],
        net_sales_cents=raw["net_sales_cents"],
        returns_cents=raw["returns_cents"],
        revenue_cents=revenue,
        cogs_cents=raw["cogs_cents"],
        gross_profit_cents=gross,
        gross_margin_bps=_margin(gross, revenue),
        expenses=dict(sorted(raw["expenses"].items())),
        other_purchases_cents=raw["other_purchases_cents"],
        shrinkage_cents=raw["shrinkage_cents"],
        operating_expenses_cents=operating,
        operating_profit_cents=gross - operating,
    )


def _merge(target: dict, source: dict) -> None:
    for key in ("net_sales_cents", "returns_cents", "cogs_cents", "other_purchases_cents", "shrinkage_cents"):
        target[key] += source[key]
    for category, value in source["expenses"].items():
        target["expenses"][category] += value


def pnl(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> PnlReport:
    since, until = _bounds(start, end)
    settings = cached_settings(db)
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    cells: dict[tuple[str, uuid.UUID], dict] = {}
    estimated = False

    def cell(moment: datetime | date, store: uuid.UUID) -> dict:
        key = (_month(moment), store)
        if key not in cells:
            cells[key] = _blank(key[0], store, stores.get(store, ""))
        return cells[key]

    sales = (
        select(Sale.created_at, Sale.store_id, SaleItem.line_total_cents, SaleItem.tax_cents, SaleItem.cost_cents)
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
    )
    returns = (
        select(
            SaleReturn.created_at,
            SaleReturn.store_id,
            ReturnItem.refund_cents,
            ReturnItem.tax_refund_cents,
            ReturnItem.quantity,
            SaleItem.cost_cents,
            SaleItem.quantity,
        )
        .join(ReturnItem, ReturnItem.return_id == SaleReturn.id)
        .join(SaleItem, SaleItem.id == ReturnItem.sale_item_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
    )
    if store_id is not None:
        sales = sales.where(Sale.store_id == store_id)
        returns = returns.where(SaleReturn.store_id == store_id)
    for created, store, line_total, tax, cost in db.execute(sales):
        row = cell(_aware(created), store)
        row["net_sales_cents"] += line_total - tax
        row["cogs_cents"] += cost or 0
        estimated = estimated or cost is None
    for created, store, refund, tax_refund, quantity, cost, sold in db.execute(returns):
        row = cell(_aware(created), store)
        row["returns_cents"] += refund - tax_refund
        row["cogs_cents"] -= (cost or 0) * quantity // max(sold, 1)

    for expense in expense_service.period_expenses(db, start, end, store_id):
        recoverable = expense_service.recoverable_tax(expense, settings.vat_registered)
        cell(expense.spent_on, expense.store_id)["expenses"][expense.category] += expense.total_cents - recoverable

    bills = (
        select(
            SupplierBill.bill_date, SupplierBill.store_id, SupplierBillLine.quantity, SupplierBillLine.unit_cost_cents
        )
        .join(SupplierBillLine, SupplierBillLine.bill_id == SupplierBill.id)
        .where(
            SupplierBill.bill_date >= start,
            SupplierBill.bill_date <= end,
            SupplierBill.status != "VOID",
            SupplierBillLine.product_id.is_(None),
        )
    )
    if store_id is not None:
        bills = bills.where(SupplierBill.store_id == store_id)
    for bill_date, store, quantity, unit_cost in db.execute(bills):
        cell(bill_date, store)["other_purchases_cents"] += quantity * unit_cost

    for moment, store, value in shrinkage(db, since, until, store_id):
        cell(moment, store)["shrinkage_cents"] += value

    rows = [_finish(raw) for _, raw in sorted(cells.items(), key=lambda item: (item[0][0], stores.get(item[0][1], "")))]
    per_store: dict[uuid.UUID, dict] = {}
    total = _blank("ALL", None, "ALL")
    for (_, store), raw in cells.items():
        per_store.setdefault(store, _blank("ALL", store, stores.get(store, "")))
        _merge(per_store[store], raw)
        _merge(total, raw)
    return PnlReport(
        period_from=start,
        period_to=end,
        currency=settings.currency,
        rows=rows,
        by_store=sorted((_finish(raw) for raw in per_store.values()), key=lambda row: row.store_code),
        total=_finish(total),
        cost_estimated=estimated,
    )


def shrinkage(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None
) -> list[tuple[datetime, uuid.UUID, int]]:
    """Stock written off (or found) by adjustments and counts, at cost."""
    return [
        (_aware(movement.created_at), movement.store_id, value)
        for movement, value in shrink_movements(db, since, until, store_id)
    ]


def shrink_movements(
    db: Session, since: datetime, until: datetime, store_id: uuid.UUID | None
) -> list[tuple[StockMovement, int]]:
    """Adjustment and count movements with their cost: positive for stock lost, negative for stock found. Weighed
    goods move in grams against per-kilogram costs."""
    query = select(StockMovement).where(
        StockMovement.created_at >= since,
        StockMovement.created_at < until,
        StockMovement.movement_type.in_(SHRINK_TYPES),
        StockMovement.reference_type.in_(SHRINK_REFERENCES),
    )
    if store_id is not None:
        query = query.where(StockMovement.store_id == store_id)
    movements = list(db.scalars(query))
    if not movements:
        return []
    added = [
        str(movement.reference_id)
        for movement in movements
        if movement.quantity > 0 and movement.reference_id is not None
    ]
    adjust_unit = {
        name: cost
        for name, cost in db.execute(
            select(PurchaseBatch.file_name, BatchItem.purchase_cost_per_unit)
            .join(BatchItem, BatchItem.batch_id == PurchaseBatch.id)
            .where(PurchaseBatch.import_source == "ADJUST", PurchaseBatch.file_name.in_(added))
        )
    } if added else {}
    allocated: dict[uuid.UUID, tuple[int, int]] = defaultdict(lambda: (0, 0))
    for movement_id, quantity, cost in db.execute(
        select(BatchAllocation.stock_movement_id, BatchAllocation.quantity, BatchItem.purchase_cost_per_unit)
        .join(BatchItem, BatchItem.id == BatchAllocation.batch_item_id)
        .where(BatchAllocation.stock_movement_id.in_([movement.id for movement in movements]))
    ):
        units, value = allocated[movement_id]
        allocated[movement_id] = (units + quantity, value + quantity * cost)
    fallback = _Costs(db)
    weighed_ids = set(
        db.scalars(
            select(Product.id).where(
                Product.id.in_({movement.product_id for movement in movements}), Product.sold_by_weight.is_(True)
            )
        )
    )
    out = []
    for movement in movements:
        reference = str(movement.reference_id) if movement.reference_id is not None else ""
        if movement.quantity > 0 and reference in adjust_unit:
            scale = weighed.GRAMS_PER_KG if movement.product_id in weighed_ids else 1
            value = weighed.amount(movement.quantity, adjust_unit[reference], scale)
            out.append((movement, -value))
            continue
        units, value = allocated.get(movement.id, (0, 0))
        rest = abs(movement.quantity) - units
        value += max(rest, 0) * (fallback(movement.product_id) or 0)
        if movement.product_id in weighed_ids:
            value = weighed.amount(value, 1, weighed.GRAMS_PER_KG)
        out.append((movement, value if movement.quantity < 0 else -value))
    return out


# --- Inventory valuation -----------------------------------------------------------------------------------


def _layers(db: Session, store_id: uuid.UUID | None) -> dict[tuple[uuid.UUID, uuid.UUID], list[tuple[int, int]]]:
    """Open FIFO layers of owned stock per (product, store), newest first: (units remaining, unit cost).
    Consignment layers belong to the supplier and are left out."""
    query = (
        select(BatchItem.product_id, BatchItem.store_id, BatchItem.quantity_remaining, BatchItem.purchase_cost_per_unit)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(
            BatchItem.quantity_remaining > 0,
            PurchaseBatch.status != "REVERSED",
            PurchaseBatch.is_consignment.is_(False),
        )
        .order_by(BatchItem.created_at.desc())
    )
    if store_id is not None:
        query = query.where(BatchItem.store_id == store_id)
    layers: dict[tuple[uuid.UUID, uuid.UUID], list[tuple[int, int]]] = defaultdict(list)
    for product_id, store, remaining, cost in db.execute(query):
        layers[(product_id, store)].append((remaining, cost))
    return layers


def _consigned_value(db: Session, store_id: uuid.UUID | None) -> int:
    """Supplier-owned stock at the price owed when it sells."""
    query = (
        select(func.coalesce(func.sum(BatchItem.quantity_remaining * BatchItem.purchase_cost_per_unit), 0))
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .where(PurchaseBatch.is_consignment.is_(True), PurchaseBatch.status != "REVERSED")
    )
    if store_id is not None:
        query = query.where(BatchItem.store_id == store_id)
    return int(db.scalar(query) or 0)


def _value(
    on_hand: int, layers: list[tuple[int, int]], fallback: int | None, *, scale: int = 1
) -> tuple[int, int, bool, bool]:
    """Cost of on-hand units: newest layers first (FIFO leaves the newest), the rest at the latest purchase cost.

    ``scale`` is 1000 for weighed goods (grams on hand, cost per kilogram) and 1 otherwise.
    Returns (cost value, units at an estimated cost, estimated?, cost missing?).
    Cost is missing when uncovered units have no fallback. A real zero fallback is not missing.
    """
    left = on_hand
    value = 0
    for remaining, cost in layers:
        take = min(left, remaining)
        value += weighed.amount(take, cost, scale)
        left -= take
        if left <= 0:
            break
    missing = False
    if left > 0:
        if fallback is None:
            missing = True
        else:
            value += weighed.amount(left, fallback, scale)
    return value, max(left, 0), left > 0, missing


def valuation(db: Session, *, store_id: uuid.UUID | None) -> ValuationReport:
    settings = cached_settings(db)
    query = (
        select(InventoryLevel, Product, Store.code)
        .join(Product, Product.id == InventoryLevel.product_id)
        .join(Store, Store.id == InventoryLevel.store_id)
        .where(InventoryLevel.quantity_on_hand > 0)
    )
    if store_id is not None:
        query = query.where(InventoryLevel.store_id == store_id)
    layers = _layers(db, store_id)
    consigned = consignment_service.consigned_units(db, store_id)
    consigned_value = _consigned_value(db, store_id)
    fallback = _Costs(db)
    rows: list[ValuationRow] = []
    estimated_units = 0
    for level, product, store_code in db.execute(query).unique():
        supplier_owned = min(level.quantity_on_hand, consigned.get((product.id, level.store_id), 0))
        owned = level.quantity_on_hand - supplier_owned
        scale = weighed.scale_of(product)
        average = level.weighted_average_cost_cents
        if costing_method(db) == "WEIGHTED_AVERAGE" and average is not None and owned:
            value = weighed.amount(owned, average, scale)
            guessed, estimated = 0, False
        else:
            value, guessed, estimated, _missing = _value(
                owned, layers.get((product.id, level.store_id), []), fallback(product.id), scale=scale
            )
        estimated_units += guessed
        rows.append(
            ValuationRow(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                store_id=level.store_id,
                store_code=store_code,
                on_hand=level.quantity_on_hand,
                unit_cost_cents=(value * scale // owned) if owned else 0,
                cost_value_cents=value,
                retail_value_cents=level.quantity_on_hand * product.price_cents,
                estimated=estimated,
                consignment_units=supplier_owned,
            )
        )
    rows.sort(key=lambda row: -row.cost_value_cents)

    def group(key) -> list[ValuationGroup]:
        totals: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])
        for row in rows:
            bucket = totals[key(row)]
            bucket[0] += row.on_hand
            bucket[1] += row.cost_value_cents
            bucket[2] += row.retail_value_cents
        return sorted(
            (
                ValuationGroup(key=name, units=v[0], cost_value_cents=v[1], retail_value_cents=v[2])
                for name, v in totals.items()
            ),
            key=lambda item: -item.cost_value_cents,
        )

    return ValuationReport(
        as_of=datetime.now(UTC),
        currency=settings.currency,
        units=sum(row.on_hand for row in rows),
        cost_value_cents=sum(row.cost_value_cents for row in rows),
        retail_value_cents=sum(row.retail_value_cents for row in rows),
        estimated_units=estimated_units,
        consignment_units=sum(row.consignment_units for row in rows),
        consignment_value_cents=consigned_value,
        by_store=group(lambda row: row.store_code),
        by_category=group(lambda row: row.category),
        rows=rows[:2000],
    )


# --- Slow and dead stock -----------------------------------------------------------------------------------


MAX_MARKDOWN_BPS = 5000


def markdown_bps(status: str, idle_days: int | None, dead_days: int) -> int:
    """Slow stock starts at 10% off, dead stock at 25%, plus 5% for every extra `dead_days` idle, capped at 50%."""
    if status == "SLOW":
        return 1000
    extra = max(0, (idle_days or dead_days) - dead_days) // max(dead_days, 1)
    return min(MAX_MARKDOWN_BPS, 2500 + 500 * extra)


def clearance_price(price: int, unit_cost: int, floor: int | None, bps: int) -> tuple[int | None, int]:
    """(suggested price, effective markdown %) or (None, 0) when the shelf price is already at the floor."""
    lowest = max(floor or 0, unit_cost)
    if price <= 0 or price <= lowest:
        return None, 0
    target = max(lowest, price - div_half_up(price * bps, 10_000))
    # Round down to the nearest 0.50 so shelf labels read cleanly, without dropping under the floor.
    rounded = max(lowest, target // 50 * 50)
    return rounded, round((price - rounded) * 100 / price)


def _classification_reason(
    *,
    status: str,
    last: datetime | None,
    days_since_sale: int | None,
    days_in_stock: int | None,
    cover: int | None,
    slow_days: int,
    dead_days: int,
) -> str:
    if last is None and days_in_stock is None:
        return "On hand with no sale and no receipt date."
    parts: list[str] = []
    if last is None:
        parts.append(f"Never sold; received {days_in_stock} days ago")
    elif days_since_sale is not None and days_since_sale >= slow_days:
        parts.append(f"No qualifying sale for {days_since_sale} days")
    if cover is not None and cover > sales_velocity.COVER_SLOW_DAYS:
        parts.append(
            f"{cover} days of cover on the last {sales_velocity.VELOCITY_WINDOW_DAYS} days of net sales"
        )
    if status == "DEAD":
        parts.append(f"Dead after {dead_days} days")
    elif status == "SLOW":
        parts.append(f"Slow after {slow_days} days without a sale, or {sales_velocity.COVER_SLOW_DAYS} days of cover")
    return "; ".join(parts)


def _expected_margin_bps(price: int | None, unit_cost: int | None) -> int | None:
    if price is None or price <= 0 or unit_cost is None:
        return None
    return round((price - unit_cost) * 10_000 / price)


def aged_stock(
    db: Session,
    *,
    store_id: uuid.UUID | None,
    slow_days: int,
    dead_days: int,
    carrying_rate_bps: int = 2500,
    q: str | None = None,
    status: str | None = None,
    category: str | None = None,
    sort: str = "cost",
    limit: int | None = None,
    offset: int = 0,
) -> AgedStockReport:
    """Slow and dead stock, what it costs to keep (capital, space, shrink: `carrying_rate_bps` a year of cost value)
    and a clearance price that respects the margin floors.

    Totals cover every row that matches the filters. ``rows`` is that list, or one page when ``limit`` is set.
    """
    if not 1 <= slow_days < dead_days <= 3650:
        raise ApiError(422, "validation_error", "Slow must be fewer days than dead, and both at most 10 years.")
    if not 0 <= carrying_rate_bps <= 10_000:
        raise ApiError(422, "validation_error", "The carrying rate is 0-100% a year.")
    if status is not None and status not in ("SLOW", "DEAD"):
        raise ApiError(422, "validation_error", "Status is slow or dead.")
    if sort not in ("cost", "idle", "cover", "name"):
        raise ApiError(422, "validation_error", "Sort by cost, idle, cover, or name.")
    if limit is not None and not 1 <= limit <= 500:
        raise ApiError(422, "validation_error", "Limit is 1 to 500.")
    if offset < 0:
        raise ApiError(422, "validation_error", "Offset cannot be negative.")
    settings = cached_settings(db)
    now = datetime.now(UTC)
    window = now - timedelta(days=sales_velocity.VELOCITY_WINDOW_DAYS)
    last_sold = sales_velocity.last_qualifying_sale(db, store_id=store_id)
    sold_90 = sales_velocity.net_units_by_store(db, since=window, until=now, store_id=store_id)
    first_stocked = (
        select(StockMovement.product_id, StockMovement.store_id, func.min(StockMovement.created_at))
        .where(StockMovement.quantity > 0)
        .group_by(StockMovement.product_id, StockMovement.store_id)
    )
    if store_id is not None:
        first_stocked = first_stocked.where(StockMovement.store_id == store_id)
    stocked = {(product_id, store): _aware(moment) for product_id, store, moment in db.execute(first_stocked)}

    query = (
        select(InventoryLevel, Product, Store.code)
        .join(Product, Product.id == InventoryLevel.product_id)
        .join(Store, Store.id == InventoryLevel.store_id)
        .where(InventoryLevel.quantity_on_hand > 0, Product.is_service.is_(False))
    )
    if store_id is not None:
        query = query.where(InventoryLevel.store_id == store_id)
    layers = _layers(db, store_id)
    consigned = consignment_service.consigned_units(db, store_id)
    fallback = _Costs(db)
    tax = tax_policy(db)
    policies = margin_service.active_policies(db)
    rows: list[AgedStockRow] = []
    for level, product, store_code in db.execute(query).unique():
        key = (product.id, level.store_id)
        last = last_sold.get(key)
        received = stocked.get(key)
        days_since_sale = (now - last).days if last else None
        days_in_stock = (now - received).days if received else None
        idle = days_since_sale if last is not None else days_in_stock
        units = sold_90.get(key, 0)
        cover = sales_velocity.cover_days(level.quantity_on_hand, units, sales_velocity.VELOCITY_WINDOW_DAYS)
        if last is None and received is None:
            row_status = "DEAD"
        elif idle is not None and idle >= dead_days:
            row_status = "DEAD"
        elif (idle is not None and idle >= slow_days) or (cover is not None and cover > sales_velocity.COVER_SLOW_DAYS):
            row_status = "SLOW"
        else:
            continue
        owned = level.quantity_on_hand - min(level.quantity_on_hand, consigned.get(key, 0))
        scale = weighed.scale_of(product)
        fallback_cost = fallback(product.id)
        value, _, estimated, missing = _value(owned, layers.get(key, []), fallback_cost, scale=scale)
        floor = (
            margin_service.floor_for(db, product, level.store_id, tax, policies) if policies != (None, {}, {}) else None
        )
        bps = markdown_bps(row_status, idle, dead_days)
        price = product.price_cents
        target_pct = bps // 100
        unit_cost: int | None = None
        suggested: int | None = None
        markdown = 0
        review = False
        limited = False
        holding_month = div_half_up(value * carrying_rate_bps, 10_000 * 12)
        holding_to_date = div_half_up(value * carrying_rate_bps * (idle or 0), 10_000 * 365)
        if owned <= 0:
            suggestion = "Supplier-owned stock. Return it to the supplier or stop replenishing it."
        elif missing:
            review = True
            suggestion = "Cost is missing. Review the purchase cost before discounting."
        else:
            unit_cost = value * scale // owned
            floor_cents = floor.floor_cents if floor else None
            suggested, markdown = clearance_price(price, unit_cost, floor_cents, bps)
            lowest = max(floor_cents or 0, unit_cost)
            limited = price > lowest and (suggested is None or markdown < target_pct)
            if suggested is not None:
                action = f"Mark down {markdown}% to {suggested / 100:,.2f}"
                if limited:
                    action = f"{action} (the {target_pct}% target stops at the cost or margin floor)"
                suggestion = (
                    f"{action} or return it to the supplier; it costs {holding_month / 100:,.2f} a month to hold."
                    if row_status == "DEAD"
                    else f"Stop reordering; {action[0].lower()}{action[1:]} or move units to a branch that sells it."
                )
            elif limited:
                suggestion = (
                    f"The {target_pct}% markdown could not be applied: "
                    "the price is already at cost or the margin floor. "
                    "Return it to the supplier or bundle it with a faster seller."
                    if row_status == "DEAD"
                    else "The markdown could not be applied: the price is already at cost or the margin floor. "
                    "Stop reordering, and move units to a branch that sells it."
                )
            else:
                suggestion = (
                    "Already priced at its floor: return it to the supplier or bundle it with a faster seller."
                    if row_status == "DEAD"
                    else "Stop reordering, and move units to a branch that sells it."
                )
        if last is None and received is None:
            suggestion = "On hand with no sale and no receipt date. Review the stock history before discounting."
        rows.append(
            AgedStockRow(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                brand=product.brand,
                sold_by_weight=product.sold_by_weight,
                store_id=level.store_id,
                store_code=store_code,
                on_hand=level.quantity_on_hand,
                cost_value_cents=value,
                last_sold_at=last,
                days_since_sale=days_since_sale,
                days_in_stock=days_in_stock,
                units_sold_90d=units,
                cover_days=cover,
                status=row_status,  # type: ignore[arg-type]
                reason=_classification_reason(
                    status=row_status,
                    last=last,
                    days_since_sale=days_since_sale,
                    days_in_stock=days_in_stock,
                    cover=cover,
                    slow_days=slow_days,
                    dead_days=dead_days,
                ),
                suggestion=suggestion,
                holding_cost_month_cents=holding_month,
                holding_cost_to_date_cents=holding_to_date,
                price_cents=price,
                suggested_price_cents=suggested,
                markdown_pct=markdown,
                target_markdown_pct=target_pct,
                floor_cents=floor.floor_cents if floor else None,
                expected_margin_bps=_expected_margin_bps(suggested, unit_cost),
                cost_estimated=estimated and not missing,
                review_required=review,
                discount_limited=limited,
            )
        )
    needle = q.strip().lower() if q and q.strip() else None
    if needle is not None:
        rows = [row for row in rows if needle in row.name.lower() or needle in row.sku.lower()]
    if status is not None:
        rows = [row for row in rows if row.status == status]
    category_name = category.strip().lower() if category and category.strip() else None
    if category_name is not None:
        rows = [row for row in rows if row.category.lower() == category_name]
    if sort == "idle":
        rows.sort(
            key=lambda row: -(
                (row.days_since_sale if row.days_since_sale is not None else row.days_in_stock) or -1
            )
        )
    elif sort == "cover":
        rows.sort(key=lambda row: -(row.cover_days if row.cover_days is not None else -1))
    elif sort == "name":
        rows.sort(key=lambda row: row.name.lower())
    else:
        rows.sort(key=lambda row: (row.status != "DEAD", -row.cost_value_cents))
    total = len(rows)
    page = rows[offset:] if limit is None else rows[offset : offset + limit]
    return AgedStockReport(
        as_of=now,
        currency=settings.currency,
        slow_days=slow_days,
        dead_days=dead_days,
        slow_value_cents=sum(row.cost_value_cents for row in rows if row.status == "SLOW"),
        dead_value_cents=sum(row.cost_value_cents for row in rows if row.status == "DEAD"),
        carrying_rate_bps=carrying_rate_bps,
        holding_cost_month_cents=sum(row.holding_cost_month_cents for row in rows),
        holding_cost_to_date_cents=sum(row.holding_cost_to_date_cents for row in rows),
        total=total,
        rows=page,
    )


# --- Sales by staff ----------------------------------------------------------------------------------------


def staff_sales(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> StaffSalesReport:
    since, until = _bounds(start, end)
    totals: dict[uuid.UUID, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    baskets: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    lines = (
        select(
            Sale.id,
            # Credited to the stylist who served the customer when one was named.
            func.coalesce(Sale.sales_associate_id, Sale.cashier_id),
            SaleItem.quantity,
            SaleItem.line_total_cents,
            SaleItem.tax_cents,
            SaleItem.cost_cents,
            SaleItem.discount_cents,
            SaleItem.list_price_cents,
            SaleItem.unit_price_cents,
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
    )
    returns = select(SaleReturn.cashier_id, SaleReturn.total_refund_cents, SaleReturn.tax_refund_cents).where(
        SaleReturn.created_at >= since, SaleReturn.created_at < until
    )
    if store_id is not None:
        lines = lines.where(Sale.store_id == store_id)
        returns = returns.where(SaleReturn.store_id == store_id)
    for sale_id, cashier, quantity, line_total, tax, cost, discount, listed, unit in db.execute(lines):
        row = totals[cashier]
        baskets[cashier].add(sale_id)
        row["units"] += quantity
        row["revenue"] += line_total - tax
        row["cogs"] += cost or 0
        row["promotion"] += discount or 0
        if listed is not None and listed > unit:
            row["override"] += (listed - unit) * quantity
    for cashier, refund, tax_refund in db.execute(returns):
        totals[cashier]["returns"] += 1
        totals[cashier]["returns_cents"] += refund - tax_refund
    names = (
        {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(list(totals)))).unique()}
        if totals
        else {}
    )
    rows = []
    for user_id, row in totals.items():
        sales = len(baskets[user_id])
        gross = row["revenue"] - row["cogs"]
        rows.append(
            StaffSalesRow(
                user_id=user_id,
                name=names.get(user_id, "Unknown"),
                sales=sales,
                units=row["units"],
                revenue_cents=row["revenue"],
                cogs_cents=row["cogs"],
                gross_profit_cents=gross,
                gross_margin_bps=_margin(gross, row["revenue"]),
                average_basket_cents=row["revenue"] // sales if sales else 0,
                promotion_discount_cents=row["promotion"],
                override_discount_cents=row["override"],
                returns=row["returns"],
                returns_cents=row["returns_cents"],
            )
        )
    rows.sort(key=lambda row: -row.revenue_cents)
    return StaffSalesReport(period_from=start, period_to=end, currency=cached_settings(db).currency, rows=rows)


# --- Cashier discounts ---------------------------------------------------------------------------------------


def discounts(db: Session, *, start: date, end: date, store_id: uuid.UUID | None) -> DiscountReport:
    """Manual discounts by cashier and reason: who gives them, why, and how many needed a manager."""
    since, until = _bounds(start, end)
    labels = {choice.key: choice.label for choice in pos_policy(db).discounts.reasons}
    totals: dict[tuple[uuid.UUID, str], dict[str, int]] = defaultdict(lambda: defaultdict(int))
    lines = (
        select(
            Sale.cashier_id,
            SaleItem.discount_reason,
            SaleItem.manual_discount_cents,
            SaleItem.discount_approved_by_id,
            SaleItem.unit_price_cents,
            SaleItem.quantity,
            SaleItem.discount_cents,
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
            SaleItem.manual_discount_cents > 0,
        )
    )
    if store_id is not None:
        lines = lines.where(Sale.store_id == store_id)
    for cashier, reason, manual, approver, unit, quantity, promotion in db.execute(lines):
        row = totals[(cashier, reason or "other")]
        row["lines"] += 1
        row["discount"] += manual
        row["before"] += unit * quantity - (promotion or 0)
        if approver is not None:
            row["approved"] += 1
    cashiers = {cashier for cashier, _ in totals}
    names = (
        {user.id: user.full_name for user in db.scalars(select(User).where(User.id.in_(list(cashiers)))).unique()}
        if cashiers
        else {}
    )

    def label(key: str) -> str:
        return labels.get(key, key.replace("_", " ").capitalize())

    rows = [
        DiscountRow(
            user_id=cashier,
            name=names.get(cashier, "Unknown"),
            reason=reason,
            reason_label=label(reason),
            lines=row["lines"],
            discount_cents=row["discount"],
            approved_lines=row["approved"],
            share_bps=_margin(row["discount"], row["before"]),
        )
        for (cashier, reason), row in totals.items()
    ]
    rows.sort(key=lambda row: -row.discount_cents)
    by_reason: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for row in rows:
        by_reason[row.reason][0] += row.lines
        by_reason[row.reason][1] += row.discount_cents
    reasons = sorted(
        (
            DiscountReasonTotal(reason=key, reason_label=label(key), lines=count, discount_cents=cents)
            for key, (count, cents) in by_reason.items()
        ),
        key=lambda item: -item.discount_cents,
    )
    return DiscountReport(
        period_from=start,
        period_to=end,
        currency=cached_settings(db).currency,
        total_cents=sum(row.discount_cents for row in rows),
        rows=rows,
        by_reason=reasons,
    )


# --- CSV ---------------------------------------------------------------------------------------------------


def _money(cents: int) -> str:
    return f"{cents / 100:.2f}"


def pnl_csv(report: PnlReport) -> str:
    categories = sorted({key for row in report.rows for key in row.expenses})
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["month", "branch", "net_sales", "returns", "revenue", "cogs", "gross_profit", "gross_margin_pct"]
        + [f"expense_{key.lower()}" for key in categories]
        + ["other_purchases", "shrinkage", "operating_expenses", "operating_profit"]
    )
    for row in [*report.rows, *report.by_store, report.total]:
        writer.writerow(
            [
                row.month,
                row.store_code,
                _money(row.net_sales_cents),
                _money(row.returns_cents),
                _money(row.revenue_cents),
                _money(row.cogs_cents),
                _money(row.gross_profit_cents),
                f"{row.gross_margin_bps / 100:.2f}",
            ]
            + [_money(row.expenses.get(key, 0)) for key in categories]
            + [
                _money(row.other_purchases_cents),
                _money(row.shrinkage_cents),
                _money(row.operating_expenses_cents),
                _money(row.operating_profit_cents),
            ]
        )
    return buffer.getvalue()


def valuation_csv(report: ValuationReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["branch", "sku", "product", "category", "on_hand", "unit_cost", "cost_value", "retail_value", "estimated"]
    )
    for row in report.rows:
        writer.writerow(
            [
                row.store_code,
                row.sku,
                row.name,
                row.category,
                row.on_hand,
                _money(row.unit_cost_cents),
                _money(row.cost_value_cents),
                _money(row.retail_value_cents),
                "yes" if row.estimated else "",
            ]
        )
    return buffer.getvalue()


def aged_csv(report: AgedStockReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "status",
            "branch",
            "sku",
            "product",
            "on_hand",
            "cost_value",
            "days_since_sale",
            "sold_90d",
            "cover_days",
            "holding_cost_month",
            "holding_cost_to_date",
            "price",
            "suggested_price",
            "markdown_pct",
            "target_markdown_pct",
            "expected_margin_pct",
            "days_in_stock",
            "reason",
            "review_required",
        ]
    )
    for row in report.rows:
        writer.writerow(
            [
                row.status,
                row.store_code,
                row.sku,
                row.name,
                row.on_hand,
                _money(row.cost_value_cents),
                row.days_since_sale if row.days_since_sale is not None else "",
                row.units_sold_90d,
                row.cover_days if row.cover_days is not None else "",
                _money(row.holding_cost_month_cents),
                _money(row.holding_cost_to_date_cents),
                _money(row.price_cents),
                _money(row.suggested_price_cents) if row.suggested_price_cents is not None else "",
                row.markdown_pct,
                row.target_markdown_pct,
                f"{row.expected_margin_bps / 100:.2f}" if row.expected_margin_bps is not None else "",
                row.days_in_stock if row.days_in_stock is not None else "",
                row.reason,
                "yes" if row.review_required else "",
            ]
        )
    return buffer.getvalue()


def discounts_csv(report: DiscountReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["staff", "reason", "lines", "discount", "manager_approved_lines", "discount_pct"])
    for row in report.rows:
        writer.writerow(
            [
                row.name,
                row.reason_label,
                row.lines,
                _money(row.discount_cents),
                row.approved_lines,
                f"{row.share_bps / 100:.2f}",
            ]
        )
    return buffer.getvalue()


def staff_csv(report: StaffSalesReport) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "staff",
            "sales",
            "units",
            "revenue",
            "cogs",
            "gross_profit",
            "margin_pct",
            "average_basket",
            "promotion_discounts",
            "price_override_discounts",
            "returns",
            "returns_value",
        ]
    )
    for row in report.rows:
        writer.writerow(
            [
                row.name,
                row.sales,
                row.units,
                _money(row.revenue_cents),
                _money(row.cogs_cents),
                _money(row.gross_profit_cents),
                f"{row.gross_margin_bps / 100:.2f}",
                _money(row.average_basket_cents),
                _money(row.promotion_discount_cents),
                _money(row.override_discount_cents),
                row.returns,
                _money(row.returns_cents),
            ]
        )
    return buffer.getvalue()
