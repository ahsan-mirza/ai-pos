"""Replenishment: nightly demand history, a per-product forecast picked by backtest (services.forecasting) with
seasonal uplift, and reorder suggestions that become draft purchase orders or transfers from a branch with surplus."""

import math
import statistics
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.batch import BatchItem, PurchaseBatch, Supplier
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.purchasing import PurchaseOrder, PurchaseOrderLine
from app.models.replenishment import DemandDaily, ReplenishmentRun, ReplenishmentSuggestion, SeasonalEvent
from app.models.return_item import ReturnItem
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.store import Store
from app.models.transfer import StockTransfer, StockTransferLine
from app.schemas.inventory import PurchaseOrderCreate, PurchaseOrderLineIn, TransferCreate, TransferLineIn
from app.schemas.replenishment import (
    AcceptResult,
    RunOut,
    SeasonalEventOut,
    SeasonalEventWrite,
    SuggestionOut,
    SupplierLeadOut,
    SupplierTermsWrite,
)
from app.services import costing, forecasting, inventory

POSTED = ("completed", "partially_refunded", "refunded")
OPEN_PO = ("ordered", "partially_received")
OPEN_TRANSFER = ("requested", "in_transit")
HISTORY_DAYS = 90
SERVICE_LEVEL_Z = 1.65


def _day_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, UTC), datetime.combine(end + timedelta(days=1), time.min, UTC)


def _as_date(value: datetime) -> date:
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(UTC).date()


def snapshot_demand(db: Session, days: int = 3, today: date | None = None) -> int:
    """Rebuilds demand_daily for the last `days` days (90 on the first run) from posted sales and returns."""
    today = today or datetime.now(UTC).date()
    if db.scalar(select(func.count()).select_from(DemandDaily)) == 0:
        days = HISTORY_DAYS
    start = today - timedelta(days=days)
    since, until = _day_bounds(start, today)
    totals: dict[tuple[uuid.UUID, uuid.UUID, date], int] = defaultdict(int)
    for product_id, store_id, created_at, quantity in db.execute(
        select(SaleItem.product_id, Sale.store_id, Sale.created_at, SaleItem.quantity)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.status.in_(POSTED),
            Sale.is_quote_proforma.is_(False),
        )
    ):
        totals[(product_id, store_id, _as_date(created_at))] += quantity
    for product_id, store_id, created_at, quantity in db.execute(
        select(ReturnItem.product_id, SaleReturn.store_id, SaleReturn.created_at, ReturnItem.quantity)
        .join(SaleReturn, SaleReturn.id == ReturnItem.return_id)
        .where(SaleReturn.created_at >= since, SaleReturn.created_at < until)
    ):
        totals[(product_id, store_id, _as_date(created_at))] -= quantity
    db.execute(delete(DemandDaily).where(DemandDaily.day >= start, DemandDaily.day <= today))
    for (product_id, store_id, day), units in totals.items():
        if units:
            db.add(DemandDaily(product_id=product_id, store_id=store_id, day=day, units=units))
    db.commit()
    return len(totals)


def _history(db: Session, store_id: uuid.UUID, today: date) -> dict[uuid.UUID, list[int]]:
    """Units per day for the last 90 days, oldest first, per product."""
    start = today - timedelta(days=HISTORY_DAYS)
    series: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0] * HISTORY_DAYS)
    for product_id, day, units in db.execute(
        select(DemandDaily.product_id, DemandDaily.day, DemandDaily.units).where(
            DemandDaily.store_id == store_id, DemandDaily.day >= start, DemandDaily.day < today
        )
    ):
        index = (day - start).days
        if 0 <= index < HISTORY_DAYS:
            series[product_id][index] = max(0, units)
    return series


def daily_rate(history: list[int]) -> float:
    """Recent weeks weigh most: 50% last 7 days, 30% last 28, 20% last 90."""
    return forecasting.weighted_average(history)


def _uplift(events: list[SeasonalEvent], product: Product, start: date, days: int) -> tuple[float, str | None]:
    if days <= 0:
        return 1.0, None
    factors = []
    names = set()
    for offset in range(days):
        day = start + timedelta(days=offset)
        factor = 1.0
        for event in events:
            applies = event.category_id is None or event.category_id == product.category_id
            if applies and event.starts_on <= day <= event.ends_on:
                factor = max(factor, event.uplift_bps / 10_000)
                names.add(event.name)
        factors.append(factor)
    multiplier = sum(factors) / len(factors)
    note = f"{', '.join(sorted(names))} (×{multiplier:.2f})" if names else None
    return multiplier, note


def _on_order(db: Session, store_id: uuid.UUID) -> dict[uuid.UUID, int]:
    pending: dict[uuid.UUID, int] = defaultdict(int)
    for product_id, ordered, received in db.execute(
        select(PurchaseOrderLine.product_id, PurchaseOrderLine.quantity_ordered, PurchaseOrderLine.quantity_received)
        .join(PurchaseOrder, PurchaseOrder.id == PurchaseOrderLine.purchase_order_id)
        .where(PurchaseOrder.destination_store_id == store_id, PurchaseOrder.status.in_(OPEN_PO))
    ):
        pending[product_id] += max(0, ordered - received)
    for product_id, quantity in db.execute(
        select(StockTransferLine.product_id, StockTransferLine.quantity)
        .join(StockTransfer, StockTransfer.id == StockTransferLine.transfer_id)
        .where(StockTransfer.destination_store_id == store_id, StockTransfer.status.in_(OPEN_TRANSFER))
    ):
        pending[product_id] += quantity
    return pending


def _preferred_supplier(db: Session, product_id: uuid.UUID) -> tuple[Supplier | None, str | None]:
    order = db.scalar(
        select(PurchaseOrder)
        .join(PurchaseOrderLine, PurchaseOrderLine.purchase_order_id == PurchaseOrder.id)
        .where(PurchaseOrderLine.product_id == product_id)
        .order_by(PurchaseOrder.created_at.desc())
        .limit(1)
    )
    if order is not None and order.supplier_id is not None:
        return db.get(Supplier, order.supplier_id), order.supplier_name
    batch_supplier = db.scalar(
        select(PurchaseBatch.supplier_id)
        .join(BatchItem, BatchItem.batch_id == PurchaseBatch.id)
        .where(BatchItem.product_id == product_id, PurchaseBatch.supplier_id.is_not(None))
        .order_by(PurchaseBatch.created_at.desc())
        .limit(1)
    )
    if batch_supplier is not None:
        supplier = db.get(Supplier, batch_supplier)
        return supplier, supplier.name if supplier else None
    if order is not None:
        supplier = db.scalar(select(Supplier).where(func.lower(Supplier.name) == order.supplier_name.lower()))
        return supplier, order.supplier_name
    return None, None


WEEKDAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")


def days_to_order(order_days: list[str] | None, today: date) -> int:
    """Days until the supplier next takes orders (0 when today is an order day or any day works)."""
    allowed = {WEEKDAYS.index(day) for day in order_days or [] if day in WEEKDAYS}
    if not allowed:
        return 0
    return next(offset for offset in range(7) if (today.weekday() + offset) % 7 in allowed)


def order_quantity(need: int, moq: int, pack_size: int) -> int:
    """Raises a need to the supplier's minimum, then up to whole cases."""
    quantity = max(need, moq, 1)
    pack = max(pack_size, 1)
    return math.ceil(quantity / pack) * pack


def _terms_note(supplier: Supplier | None, need: int, ordered: int, wait: int, today: date) -> str | None:
    if supplier is None:
        return None
    parts = []
    if ordered != need:
        if supplier.moq > 1 and ordered >= supplier.moq > need:
            parts.append(f"MOQ {supplier.moq}")
        if supplier.pack_size > 1:
            parts.append(f"cases of {supplier.pack_size}")
    if wait:
        parts.append(f"next order day {(today + timedelta(days=wait)):%a} (+{wait}d)")
    return " · ".join(parts) or None


def create_run(
    db: Session,
    *,
    store_id: uuid.UUID,
    review_days: int,
    user_id: uuid.UUID | None,
    split_by_size_curve: bool = False,
) -> RunOut:
    store = db.get(Store, store_id)
    if store is None:
        raise ApiError(404, "not_found", "Store was not found.")
    today = datetime.now(UTC).date()
    snapshot_demand(db, days=3, today=today)
    history = _history(db, store_id, today)
    levels = {
        row.product_id: row for row in db.scalars(select(InventoryLevel).where(InventoryLevel.store_id == store_id))
    }
    pending = _on_order(db, store_id)
    events = list(db.scalars(select(SeasonalEvent).where(SeasonalEvent.is_active.is_(True))))
    others = {row.id: row for row in db.scalars(select(Store).where(Store.id != store_id, Store.is_active.is_(True)))}
    other_levels: dict[uuid.UUID, list[InventoryLevel]] = defaultdict(list)
    if others:
        for row in db.scalars(select(InventoryLevel).where(InventoryLevel.store_id.in_(list(others)))):
            other_levels[row.product_id].append(row)

    run = ReplenishmentRun(store_id=store_id, review_days=review_days, created_by_id=user_id)
    db.add(run)
    db.flush()
    products = db.scalars(select(Product).where(Product.is_open_price.is_(False), Product.is_service.is_(False)))
    for product in products:
        level = levels.get(product.id)
        series = history.get(product.id, [0] * HISTORY_DAYS)
        min_level = level.min_reorder_level if level is not None else 0
        if not any(series) and min_level <= 0:
            continue
        supplier, supplier_name = _preferred_supplier(db, product.id)
        lead = supplier.lead_time_days if supplier is not None else 7
        wait = days_to_order(supplier.order_days, today) if supplier is not None else 0
        # Stock has to last until the next order day, then through delivery and the review period.
        cover = wait + lead + review_days
        predicted = forecasting.forecast(series, today - timedelta(days=1), cover)
        rate = predicted.rate
        if rate <= 0 and min_level <= 0:
            continue
        multiplier, note = _uplift(events, product, today, cover)
        forecast = math.ceil(predicted.total * multiplier)
        spread = statistics.pstdev(series[-28:]) if any(series[-28:]) else 0.0
        safety = math.ceil(SERVICE_LEVEL_Z * spread * math.sqrt(lead))
        on_hand = level.quantity_on_hand if level is not None else 0
        reserved = level.quantity_reserved if level is not None else 0
        on_order = pending.get(product.id, 0)
        target = max(forecast + safety, min_level)
        if level is not None and level.max_stock_level:
            target = min(target, level.max_stock_level)
        need = target - (on_hand - reserved + on_order)
        if need <= 0:
            continue
        cost = costing.fallback_unit_cost(db, product.id) or 0
        base = {
            "run_id": run.id,
            "product_id": product.id,
            "store_id": store_id,
            "on_hand": on_hand,
            "on_order": on_order,
            "daily_rate_milli": round(rate * multiplier * 1000),
            "lead_time_days": lead,
            "forecast_units": forecast,
            "safety_stock": safety,
            "unit_cost_cents": cost,
            "seasonal_note": note,
            "forecast_method": predicted.method,
            "forecast_accuracy_bps": round(predicted.accuracy * 10_000) if predicted.accuracy is not None else None,
            "trend_pct_week": round(predicted.trend_pct_week) if predicted.trend_pct_week is not None else None,
        }
        donor = max(
            (
                row
                for row in other_levels.get(product.id, [])
                if row.quantity_on_hand - row.quantity_reserved - row.min_reorder_level > 0
            ),
            key=lambda row: (others[row.store_id].is_warehouse, row.quantity_on_hand - row.quantity_reserved),
            default=None,
        )
        if donor is not None:
            surplus = donor.quantity_on_hand - donor.quantity_reserved - donor.min_reorder_level
            moved = min(need, surplus)
            db.add(
                ReplenishmentSuggestion(**base, source="TRANSFER", from_store_id=donor.store_id, suggested_qty=moved)
            )
            need -= moved
        if need > 0:
            ordered = order_quantity(need, supplier.moq, supplier.pack_size) if supplier is not None else need
            db.add(
                ReplenishmentSuggestion(
                    **base,
                    source="PURCHASE",
                    supplier_id=supplier.id if supplier is not None else None,
                    supplier_name=supplier_name,
                    suggested_qty=ordered,
                    terms_note=_terms_note(supplier, need, ordered, wait, today),
                )
            )
    if split_by_size_curve:
        _split_by_curve(db, run)
    db.commit()
    return run_out(db, run)


def _split_by_curve(db: Session, run: ReplenishmentRun) -> None:
    """Spread each model's suggested units across its sizes by their share of recent sales."""
    from app.services import size_curve_service

    suggestions = list(db.scalars(select(ReplenishmentSuggestion).where(ReplenishmentSuggestion.run_id == run.id)))
    if not suggestions:
        return
    products = {
        row.id: row
        for row in db.scalars(select(Product).where(Product.id.in_({row.product_id for row in suggestions})))
    }
    groups: dict[uuid.UUID, list[ReplenishmentSuggestion]] = defaultdict(list)
    for suggestion in suggestions:
        model_id = products[suggestion.product_id].product_model_id if suggestion.product_id in products else None
        if model_id is not None:
            groups[model_id].append(suggestion)
    for rows in groups.values():
        if len({row.product_id for row in rows}) < 2:
            continue
        shares = size_curve_service.sales_shares(db, list({row.product_id for row in rows}))
        for source in ("PURCHASE", "TRANSFER"):
            batch = [row for row in rows if row.source == source]
            total = sum(row.suggested_qty for row in batch)
            if total <= 0 or len(batch) < 2:
                continue
            weights = [shares.get(row.product_id, 0) for row in batch]
            if sum(weights) <= 0:
                weights = [1] * len(batch)
            raw = [total * weight for weight in weights]
            whole = sum(raw) or 1
            allocated = [quantity * total // whole for quantity in raw]
            allocated[-1] += total - sum(allocated)
            for row, quantity in zip(batch, allocated, strict=True):
                row.suggested_qty = max(quantity, 0)


def run_out(db: Session, run: ReplenishmentRun) -> RunOut:
    rows = list(
        db.scalars(
            select(ReplenishmentSuggestion)
            .where(ReplenishmentSuggestion.run_id == run.id)
            .order_by(ReplenishmentSuggestion.source, ReplenishmentSuggestion.supplier_name)
        )
    )
    products = (
        {row.id: row for row in db.scalars(select(Product).where(Product.id.in_({item.product_id for item in rows})))}
        if rows
        else {}
    )
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    suggestions = [
        SuggestionOut(
            id=row.id,
            product_id=row.product_id,
            product_name=products[row.product_id].name if row.product_id in products else "",
            sku=products[row.product_id].sku if row.product_id in products else "",
            source=row.source,  # type: ignore[arg-type]
            supplier_id=row.supplier_id,
            supplier_name=row.supplier_name,
            from_store_code=stores.get(row.from_store_id) if row.from_store_id else None,
            on_hand=row.on_hand,
            on_order=row.on_order,
            daily_rate=row.daily_rate_milli / 1000,
            lead_time_days=row.lead_time_days,
            forecast_units=row.forecast_units,
            safety_stock=row.safety_stock,
            suggested_qty=row.suggested_qty,
            unit_cost_cents=row.unit_cost_cents,
            seasonal_note=row.seasonal_note,
            terms_note=row.terms_note,
            forecast_method=row.forecast_method,
            forecast_method_label=forecasting.METHOD_LABELS.get(row.forecast_method or ""),
            forecast_accuracy=row.forecast_accuracy_bps / 10_000 if row.forecast_accuracy_bps is not None else None,
            trend_pct_week=row.trend_pct_week,
            status=row.status,  # type: ignore[arg-type]
            purchase_order_id=row.purchase_order_id,
            transfer_id=row.transfer_id,
        )
        for row in rows
    ]
    created = run.created_at if run.created_at.tzinfo else run.created_at.replace(tzinfo=UTC)
    return RunOut(
        id=run.id,
        store_id=run.store_id,
        store_code=stores.get(run.store_id, ""),
        review_days=run.review_days,
        created_at=created,
        purchase_value_cents=sum(
            item.suggested_qty * item.unit_cost_cents
            for item in rows
            if item.source == "PURCHASE" and item.status != "DISMISSED"
        ),
        suggestions=suggestions,
    )


def latest_run(db: Session, store_id: uuid.UUID) -> RunOut | None:
    run = db.scalar(
        select(ReplenishmentRun)
        .where(ReplenishmentRun.store_id == store_id)
        .order_by(ReplenishmentRun.created_at.desc())
        .limit(1)
    )
    return run_out(db, run) if run is not None else None


def accept(
    db: Session,
    settings: Settings,
    principal: Principal,
    run_id: uuid.UUID,
    quantities: dict[uuid.UUID, int],
) -> AcceptResult:
    run = db.get(ReplenishmentRun, run_id)
    if run is None:
        raise ApiError(404, "not_found", "Replenishment run was not found.")
    rows = list(
        db.scalars(
            select(ReplenishmentSuggestion).where(
                ReplenishmentSuggestion.run_id == run_id,
                ReplenishmentSuggestion.id.in_(list(quantities)),
                ReplenishmentSuggestion.status == "PENDING",
            )
        )
    )
    if not rows:
        raise ApiError(422, "validation_error", "Choose at least one pending suggestion.")
    purchases: dict[str, list[ReplenishmentSuggestion]] = defaultdict(list)
    transfers: dict[uuid.UUID, list[ReplenishmentSuggestion]] = defaultdict(list)
    for row in rows:
        quantity = quantities[row.id]
        if quantity <= 0:
            continue
        row.suggested_qty = quantity
        if row.source == "TRANSFER" and row.from_store_id is not None:
            transfers[row.from_store_id].append(row)
        else:
            purchases[row.supplier_name or "Supplier to be confirmed"].append(row)
    order_ids: list[uuid.UUID] = []
    transfer_ids: list[uuid.UUID] = []
    for supplier_name, items in purchases.items():
        order = inventory.create_purchase_order(
            db,
            principal,
            PurchaseOrderCreate(
                supplier_name=supplier_name if len(supplier_name) >= 2 else "Supplier",
                destination_store_id=run.store_id,
                notes="Drafted from replenishment suggestions.",
                lines=[
                    PurchaseOrderLineIn(
                        product_id=item.product_id,
                        quantity_ordered=item.suggested_qty,
                        unit_cost_cents=item.unit_cost_cents,
                    )
                    for item in items
                ],
            ),
        )
        stored = db.get(PurchaseOrder, order.id)
        if stored is not None and items[0].supplier_id is not None:
            stored.supplier_id = items[0].supplier_id
        for item in items:
            item.status = "ACCEPTED"
            item.purchase_order_id = order.id
        order_ids.append(order.id)
    for from_store, items in transfers.items():
        transfer = inventory.create_transfer(
            db,
            settings,
            principal,
            TransferCreate(
                source_store_id=from_store,
                destination_store_id=run.store_id,
                note="Requested from replenishment suggestions.",
                lines=[TransferLineIn(product_id=item.product_id, quantity=item.suggested_qty) for item in items],
            ),
        )
        for item in items:
            item.status = "ACCEPTED"
            item.transfer_id = transfer.id
        transfer_ids.append(transfer.id)
    db.commit()
    return AcceptResult(purchase_order_ids=order_ids, transfer_ids=transfer_ids, run=run_out(db, run))


def dismiss(db: Session, suggestion_id: uuid.UUID) -> RunOut:
    row = db.get(ReplenishmentSuggestion, suggestion_id)
    if row is None:
        raise ApiError(404, "not_found", "Suggestion was not found.")
    if row.status == "PENDING":
        row.status = "DISMISSED"
    db.commit()
    run = db.get(ReplenishmentRun, row.run_id)
    assert run is not None
    return run_out(db, run)


def list_events(db: Session) -> list[SeasonalEventOut]:
    return [
        SeasonalEventOut.model_validate(row)
        for row in db.scalars(select(SeasonalEvent).order_by(SeasonalEvent.starts_on))
    ]


def save_event(db: Session, data: SeasonalEventWrite, event_id: uuid.UUID | None = None) -> list[SeasonalEventOut]:
    row = db.get(SeasonalEvent, event_id) if event_id else None
    if event_id and row is None:
        raise ApiError(404, "not_found", "Event was not found.")
    if row is None:
        row = SeasonalEvent()
        db.add(row)
    row.name = data.name.strip()
    row.starts_on = data.starts_on
    row.ends_on = data.ends_on
    row.uplift_bps = data.uplift_bps
    row.category_id = data.category_id
    row.is_active = data.is_active
    db.commit()
    return list_events(db)


def delete_event(db: Session, event_id: uuid.UUID) -> list[SeasonalEventOut]:
    row = db.get(SeasonalEvent, event_id)
    if row is None:
        raise ApiError(404, "not_found", "Event was not found.")
    db.delete(row)
    db.commit()
    return list_events(db)


def suppliers(db: Session) -> list[SupplierLeadOut]:
    return [
        SupplierLeadOut(
            id=row.id,
            name=row.name,
            code=row.code,
            lead_time_days=row.lead_time_days,
            moq=row.moq or 1,
            pack_size=row.pack_size or 1,
            order_days=[day for day in row.order_days or [] if day in WEEKDAYS],
        )
        for row in db.scalars(select(Supplier).where(Supplier.is_active.is_(True)).order_by(Supplier.name))
    ]


def set_lead_time(db: Session, supplier_id: uuid.UUID, days: int) -> list[SupplierLeadOut]:
    row = db.get(Supplier, supplier_id)
    if row is None:
        raise ApiError(404, "not_found", "Supplier was not found.")
    row.lead_time_days = days
    db.commit()
    return suppliers(db)


def set_terms(db: Session, supplier_id: uuid.UUID, data: SupplierTermsWrite) -> list[SupplierLeadOut]:
    row = db.get(Supplier, supplier_id)
    if row is None:
        raise ApiError(404, "not_found", "Supplier was not found.")
    row.lead_time_days = data.lead_time_days
    row.moq = data.moq
    row.pack_size = data.pack_size
    row.order_days = [day for day in WEEKDAYS if day in set(data.order_days)]
    db.commit()
    return suppliers(db)
