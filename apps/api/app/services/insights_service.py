"""AI insights (statistical, explainable): loss-prevention anomalies per cashier, price suggestions, and shrink
analytics. Every figure comes from the ledgers (sales, returns, audit trail, shifts, stock movements); each signal
says why it fired so a manager can check it."""

from __future__ import annotations

import statistics
import time
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.core.permissions import Permission
from app.models.audit_log import AuditLog
from app.models.batch import BatchItem, PurchaseBatch
from app.models.inventory import InventoryLevel
from app.models.product import Product
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.sale_return import SaleReturn
from app.models.shift import RegisterShift
from app.models.store import Store
from app.models.user import User
from app.schemas.insights import (
    Anomaly,
    AnomalyReport,
    InsightFeed,
    InsightItem,
    PriceSuggestion,
    PricingReport,
    ShrinkHotspot,
    ShrinkProduct,
    ShrinkReport,
    ShrinkSlice,
    ShrinkWeek,
    StaffActivity,
)
from app.services import management_reports, margin_service, weighed
from app.services.settings_service import cached_settings
from app.services.tax import policy as tax_policy

POSTED = ("completed", "partially_refunded", "refunded")

# --- Anomalies ---------------------------------------------------------------------------------------------------

# A cashier needs this many sales in the window before their rates are compared with anyone's.
MIN_SALES = 10
# Peer comparison needs at least this many comparable cashiers; with fewer, fixed ceilings apply instead.
MIN_PEERS = 3
MEDIUM_SCORE = 3.0
HIGH_SCORE = 5.0
# Ceilings (events per 100 sales) used when there are too few peers to compare against.
CEILINGS = {"VOIDS": 5.0, "NO_SALES": 3.0, "REFUNDS": 5.0, "PRICE_OVERRIDES": 10.0}
RATE_LABELS = {
    "VOIDS": "voided items",
    "NO_SALES": "no-sale drawer opens",
    "REFUNDS": "refunds",
    "PRICE_OVERRIDES": "price overrides",
}
# A closed shift counts as short (or over) when the drawer is off by more than this.
CASH_TOLERANCE_CENTS = 500


def _since(days: int) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only see your own store.")
        return principal.store_id
    return store_id


def _money(cents: int, currency: str) -> str:
    return f"{currency} {cents / 100:,.2f}"


def _counts(db: Session, statement, store_column, store_id: uuid.UUID | None) -> dict[uuid.UUID, int]:  # type: ignore[no-untyped-def]
    if store_id is not None:
        statement = statement.where(store_column == store_id)
    return {row[0]: int(row[1]) for row in db.execute(statement) if row[0] is not None}


def _activity(
    db: Session, since: datetime, store_id: uuid.UUID | None
) -> tuple[list[StaffActivity], dict[uuid.UUID, list[int]]]:
    sales = _counts(
        db,
        select(Sale.cashier_id, func.count())
        .where(Sale.created_at >= since, Sale.is_quote_proforma.is_(False), Sale.status.in_(POSTED))
        .group_by(Sale.cashier_id),
        Sale.store_id,
        store_id,
    )

    def audited(action_type: str) -> dict[uuid.UUID, int]:
        return _counts(
            db,
            select(AuditLog.user_id, func.count())
            .where(AuditLog.action_type == action_type, AuditLog.occurred_at >= since)
            .group_by(AuditLog.user_id),
            AuditLog.store_id,
            store_id,
        )

    voids, no_sales, overrides = audited("ITEM_VOID"), audited("DRAWER_OPEN"), audited("PRICE_OVERRIDE")
    refunds: dict[uuid.UUID, tuple[int, int]] = {}
    refund_query = (
        select(SaleReturn.cashier_id, func.count(), func.coalesce(func.sum(SaleReturn.total_refund_cents), 0))
        .where(SaleReturn.created_at >= since)
        .group_by(SaleReturn.cashier_id)
    )
    if store_id is not None:
        refund_query = refund_query.where(SaleReturn.store_id == store_id)
    for cashier, count, cents in db.execute(refund_query):
        refunds[cashier] = (int(count), int(cents))
    cash: dict[uuid.UUID, list[int]] = defaultdict(list)
    shift_query = select(RegisterShift.opened_by_id, RegisterShift.variance_cents).where(
        RegisterShift.closed_at >= since, RegisterShift.variance_cents.is_not(None)
    )
    if store_id is not None:
        shift_query = shift_query.where(RegisterShift.store_id == store_id)
    for user_id, variance in db.execute(shift_query):
        cash[user_id].append(int(variance))

    people = set(sales) | set(voids) | set(no_sales) | set(overrides) | set(refunds) | set(cash)
    names = {row.id: row.full_name for row in db.scalars(select(User).where(User.id.in_(people)))} if people else {}
    rows = [
        StaffActivity(
            user_id=user_id,
            user_name=names.get(user_id, "Unknown user"),
            sales=sales.get(user_id, 0),
            voids=voids.get(user_id, 0),
            no_sales=no_sales.get(user_id, 0),
            refunds=refunds.get(user_id, (0, 0))[0],
            refund_cents=refunds.get(user_id, (0, 0))[1],
            price_overrides=overrides.get(user_id, 0),
            shifts_closed=len(cash.get(user_id, [])),
            cash_short_cents=sum(-value for value in cash.get(user_id, []) if value < 0),
            cash_over_cents=sum(value for value in cash.get(user_id, []) if value > 0),
        )
        for user_id in people
    ]
    rows.sort(key=lambda row: (-row.sales, row.user_name))
    return rows, cash


def _rate_counts(row: StaffActivity) -> dict[str, int]:
    return {
        "VOIDS": row.voids,
        "NO_SALES": row.no_sales,
        "REFUNDS": row.refunds,
        "PRICE_OVERRIDES": row.price_overrides,
    }


def robust_score(value: float, peers: list[float]) -> tuple[float, float]:
    """(peer median, robust z-score). The spread floor keeps a quiet team (everyone near zero) from flagging one
    cashier for a single extra event."""
    median = statistics.median(peers)
    mad = statistics.median(abs(peer - median) for peer in peers)
    spread = max(1.4826 * mad, 1.0, 0.25 * median)
    return median, (value - median) / spread


def anomalies(db: Session, principal: Principal, *, days: int = 30, store_id: uuid.UUID | None = None) -> AnomalyReport:
    if not 7 <= days <= 365:
        raise ApiError(422, "validation_error", "Look back between 7 and 365 days.")
    return detect_anomalies(db, days=days, scope=_scope(principal, store_id))


def detect_anomalies(db: Session, *, days: int, scope: uuid.UUID | None) -> AnomalyReport:
    currency = cached_settings(db).currency
    staff, cash = _activity(db, _since(days), scope)
    eligible = [row for row in staff if row.sales >= MIN_SALES]
    found: list[Anomaly] = []
    for kind, label in RATE_LABELS.items():
        rates = {row.user_id: _rate_counts(row)[kind] * 100 / row.sales for row in eligible}
        for row in eligible:
            count = _rate_counts(row)[kind]
            if count < 3:
                continue
            rate = rates[row.user_id]
            others = [value for user_id, value in rates.items() if user_id != row.user_id]
            if len(others) >= MIN_PEERS:
                median, score = robust_score(rate, others)
                if score < MEDIUM_SCORE:
                    continue
                severity = "HIGH" if score >= HIGH_SCORE and count >= 5 else "MEDIUM"
                summary = (
                    f"{row.user_name}: {count} {label} in {row.sales} sales ({rate:.1f} per 100), "
                    f"{rate / median:.1f}x the team median of {median:.1f}."
                    if median > 0
                    else f"{row.user_name}: {count} {label} in {row.sales} sales ({rate:.1f} per 100); "
                    "the rest of the team has almost none."
                )
            else:
                ceiling = CEILINGS[kind]
                if rate <= ceiling:
                    continue
                median, score = None, None
                severity = "HIGH" if rate >= 2 * ceiling else "MEDIUM"
                summary = (
                    f"{row.user_name}: {count} {label} in {row.sales} sales ({rate:.1f} per 100), "
                    f"above the {ceiling:g} per 100 a store usually sees."
                )
            found.append(
                Anomaly(
                    kind=kind,  # type: ignore[arg-type]
                    severity=severity,  # type: ignore[arg-type]
                    user_id=row.user_id,
                    user_name=row.user_name,
                    count=count,
                    sales=row.sales,
                    rate=round(rate, 2),
                    peer_rate=round(median, 2) if median is not None else None,
                    score=round(score, 1) if score is not None else None,
                    amount_cents=row.refund_cents if kind == "REFUNDS" else None,
                    summary=summary,
                )
            )
    for row in staff:
        variances = cash.get(row.user_id, [])
        short = [value for value in variances if value < -CASH_TOLERANCE_CENTS]
        over = [value for value in variances if value > CASH_TOLERANCE_CENTS]
        short_total = -sum(short)
        if len(short) >= 2 or short_total >= 5_000:
            severity = "HIGH" if len(short) >= 4 or short_total >= 20_000 else "MEDIUM"
            found.append(
                Anomaly(
                    kind="CASH_SHORT",
                    severity=severity,  # type: ignore[arg-type]
                    user_id=row.user_id,
                    user_name=row.user_name,
                    count=len(short),
                    sales=row.sales,
                    rate=None,
                    peer_rate=None,
                    score=None,
                    amount_cents=short_total,
                    summary=(
                        f"{row.user_name}: drawer short on {len(short)} of {len(variances)} closed shifts, "
                        f"{_money(short_total, currency)} in total."
                    ),
                )
            )
        if len(over) >= 3:
            found.append(
                Anomaly(
                    kind="CASH_OVER",
                    severity="MEDIUM",
                    user_id=row.user_id,
                    user_name=row.user_name,
                    count=len(over),
                    sales=row.sales,
                    rate=None,
                    peer_rate=None,
                    score=None,
                    amount_cents=sum(over),
                    summary=(
                        f"{row.user_name}: drawer over on {len(over)} of {len(variances)} closed shifts "
                        f"({_money(sum(over), currency)}); cash taken without ringing a sale shows up this way."
                    ),
                )
            )
    found.sort(key=lambda item: (item.severity != "HIGH", -(item.score or 0), -(item.amount_cents or 0)))
    return AnomalyReport(
        as_of=datetime.now(UTC), days=days, currency=currency, peers=len(eligible), staff=staff, anomalies=found
    )


# --- Price suggestions -------------------------------------------------------------------------------------------

DEMAND_DAYS = 28
BASELINE_DAYS = 56
# Fast sellers: at least this many units in the last 28 days, selling this much faster than the 8 weeks before.
DEMAND_MIN_UNITS = 10
DEMAND_GROWTH = 1.5
DEMAND_MAX_COVER_DAYS = 14
EXPIRY_HORIZON_DAYS = 7


def _round_up(cents: int) -> int:
    return -(-cents // 50) * 50


def expiry_markdown_bps(days_left: int) -> int:
    """20% a week out, 30% within three days, half price on the last day."""
    if days_left <= 1:
        return 5000
    if days_left <= 3:
        return 3000
    return 2000


def _units(db: Session, since: datetime, until: datetime, scope: uuid.UUID | None) -> dict[uuid.UUID, int]:
    query = (
        select(SaleItem.product_id, func.coalesce(func.sum(SaleItem.quantity), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(SaleItem.product_id)
    )
    if scope is not None:
        query = query.where(Sale.store_id == scope)
    return {product_id: int(units) for product_id, units in db.execute(query)}


def pricing(
    db: Session,
    principal: Principal,
    *,
    store_id: uuid.UUID | None = None,
    limit: int = 100,
    include_clearance: bool = True,
) -> PricingReport:
    scope = _scope(principal, store_id)
    currency = cached_settings(db).currency
    now = datetime.now(UTC)
    recent = _units(db, now - timedelta(days=DEMAND_DAYS), now, scope)
    baseline = _units(db, now - timedelta(days=DEMAND_DAYS + BASELINE_DAYS), now - timedelta(days=DEMAND_DAYS), scope)
    stock_query = select(
        InventoryLevel.product_id, func.coalesce(func.sum(InventoryLevel.quantity_on_hand), 0)
    ).group_by(InventoryLevel.product_id)
    if scope is not None:
        stock_query = stock_query.where(InventoryLevel.store_id == scope)
    on_hand = {product_id: int(units) for product_id, units in db.execute(stock_query)}
    stores = {row.id: row for row in db.scalars(select(Store).where(Store.is_active.is_(True)))}
    store_code = stores[scope].code if scope is not None and scope in stores else None
    suggestions: list[PriceSuggestion] = []

    def add(product: Product, action: str, suggested: int, reason: str, **extra: object) -> None:
        units = recent.get(product.id, 0)
        stock = int(extra.pop("on_hand", on_hand.get(product.id, 0)))  # type: ignore[call-overload]
        daily = units / DEMAND_DAYS
        suggestions.append(
            PriceSuggestion(
                product_id=product.id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                store_code=extra.pop("store_code", store_code),  # type: ignore[arg-type]
                action=action,  # type: ignore[arg-type]
                price_cents=product.price_cents,
                suggested_price_cents=suggested,
                change_pct=round((suggested - product.price_cents) * 100 / product.price_cents),
                reason=reason,
                units_28d=units,
                on_hand=stock,
                cover_days=round(stock / daily) if daily else None,
                expiry_date=extra.pop("expiry_date", None),  # type: ignore[arg-type]
                sold_by_weight=product.sold_by_weight,
            )
        )

    selling = list(
        db.scalars(
            select(Product).where(
                Product.id.in_(recent.keys()),
                Product.is_service.is_(False),
                Product.is_open_price.is_(False),
                Product.price_cents > 0,
            )
        ).unique()
    )
    policies = margin_service.active_policies(db)
    tax = tax_policy(db)
    floor_stores = [scope] if scope is not None else list(stores)
    raised: set[uuid.UUID] = set()
    if policies != (None, {}, {}):
        for product in selling:
            floors = [
                floor
                for store in floor_stores
                if (floor := margin_service.floor_for(db, product, store, tax, policies)) is not None
            ]
            if not floors:
                continue
            floor = max(floors, key=lambda item: item.floor_cents)
            if product.price_cents >= floor.floor_cents:
                continue
            raised.add(product.id)
            add(
                product,
                "RAISE_TO_FLOOR",
                _round_up(floor.floor_cents),
                f"Selling under its {floor.min_margin_bps / 100:g}% margin floor: the next unit costs "
                f"{_money(floor.cost_cents, currency)}{' (estimated)' if floor.cost_estimated else ''}.",
            )
    for product in selling:
        if product.id in raised:
            continue
        units = recent.get(product.id, 0)
        if units < DEMAND_MIN_UNITS:
            continue
        before = baseline.get(product.id, 0) * DEMAND_DAYS / BASELINE_DAYS
        growth = units / before if before else None
        stock = on_hand.get(product.id, 0)
        cover = stock / (units / DEMAND_DAYS)
        if growth is None or growth < DEMAND_GROWTH or cover > DEMAND_MAX_COVER_DAYS:
            continue
        bps = 1000 if growth >= 3 else 500
        add(
            product,
            "RAISE_ON_DEMAND",
            _round_up(product.price_cents + product.price_cents * bps // 10_000),
            f"Selling {growth:.1f}x faster than the 8 weeks before with about {round(cover)} days of stock left; "
            f"a {bps // 100}% rise slows the run on the shelf until the next delivery.",
        )

    today = now.date()
    expiring = (
        select(BatchItem, Product)
        .join(PurchaseBatch, PurchaseBatch.id == BatchItem.batch_id)
        .join(Product, Product.id == BatchItem.product_id)
        .where(
            BatchItem.quantity_remaining > 0,
            BatchItem.expiry_date.is_not(None),
            BatchItem.expiry_date >= today,
            BatchItem.expiry_date <= today + timedelta(days=EXPIRY_HORIZON_DAYS),
            PurchaseBatch.status != "REVERSED",
            Product.price_cents > 0,
        )
        .order_by(BatchItem.expiry_date)
    )
    if scope is not None:
        expiring = expiring.where(BatchItem.store_id == scope)
    for item, product in db.execute(expiring).unique():
        assert item.expiry_date is not None
        days_left = (item.expiry_date - today).days
        daily = recent.get(product.id, 0) / DEMAND_DAYS
        expected = daily * (days_left + 1)
        surplus = item.quantity_remaining - expected
        if surplus <= 0:
            continue
        suggested, pct = management_reports.clearance_price(
            product.price_cents, 0, None, expiry_markdown_bps(days_left)
        )
        if suggested is None:
            continue
        surplus_label = weighed.format_weight(round(surplus)) if product.sold_by_weight else f"{round(surplus)} units"
        add(
            product,
            "EXPIRY_MARKDOWN",
            suggested,
            f"Expires {item.expiry_date.isoformat()} ({days_left} days); at the current pace about {surplus_label} "
            f"would be left to write off. Mark down {pct}% to sell through.",
            on_hand=item.quantity_remaining,
            expiry_date=item.expiry_date,
            store_code=stores[item.store_id].code if item.store_id in stores else None,
        )

    aged = (
        management_reports.aged_stock(db, store_id=scope, slow_days=60, dead_days=120).rows if include_clearance else []
    )
    aged_ids = {row.product_id for row in aged}
    by_id = {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(aged_ids))).unique()}
    cleared: dict[uuid.UUID, PriceSuggestion] = {}
    for row in aged:
        product = by_id.get(row.product_id)
        if product is None or row.suggested_price_cents is None or row.suggested_price_cents >= product.price_cents:
            continue
        if product.id in cleared:
            # Prices are chain-wide: one clearance decision per product, naming every branch holding it.
            earlier = cleared[product.id]
            earlier.store_code = f"{earlier.store_code}, {row.store_code}" if earlier.store_code else row.store_code
            earlier.on_hand += row.on_hand
            continue
        idle = f"no sale in {row.days_since_sale} days" if row.days_since_sale is not None else "never sold"
        add(
            product,
            "CLEARANCE",
            row.suggested_price_cents,
            f"{row.status.title()} stock ({idle}); holding it costs {_money(row.holding_cost_month_cents, currency)} "
            f"a month. Clearance price stays above cost and the margin floor.",
            on_hand=row.on_hand,
            store_code=row.store_code,
        )
        cleared[product.id] = suggestions[-1]

    order = {"RAISE_TO_FLOOR": 0, "EXPIRY_MARKDOWN": 1, "RAISE_ON_DEMAND": 2, "CLEARANCE": 3}
    suggestions.sort(key=lambda item: (order[item.action], item.expiry_date or date.max, -abs(item.change_pct)))
    counts: dict[str, int] = defaultdict(int)
    for item in suggestions:
        counts[item.action] += 1
    return PricingReport(as_of=now, currency=currency, counts=dict(counts), suggestions=suggestions[:limit])


# --- Shrink ------------------------------------------------------------------------------------------------------

REASON_LABELS = {
    "DAMAGED_OR_EXPIRED": "Damaged or expired",
    "STOLEN_SHRINKAGE": "Theft",
    "PHYSICAL_COUNT_AUDIT": "Stock count difference",
}
# Retail rule of thumb: net shrink above ~1.5% of sales deserves attention; a category at twice the store's rate
# (and at least that benchmark) is a hotspot.
BENCHMARK_BPS = 150


def _share(part: int, whole: int) -> int:
    return round(part * 10_000 / whole) if whole else 0


def shrink(db: Session, principal: Principal, *, days: int = 90, store_id: uuid.UUID | None = None) -> ShrinkReport:
    if not 7 <= days <= 730:
        raise ApiError(422, "validation_error", "Look back between 7 and 730 days.")
    scope = _scope(principal, store_id)
    currency = cached_settings(db).currency
    until = datetime.now(UTC)
    since = until - timedelta(days=days)
    events = management_reports.shrink_movements(db, since, until, scope)
    product_ids = {movement.product_id for movement, _ in events}
    products = (
        {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(product_ids))).unique()}
        if product_ids
        else {}
    )
    stores = {row.id: row.code for row in db.scalars(select(Store))}
    lost = found = 0
    by_reason: dict[str, int] = defaultdict(int)
    by_category: dict[str, int] = defaultdict(int)
    by_store: dict[str, int] = defaultdict(int)
    per_product: dict[uuid.UUID, list[int]] = defaultdict(lambda: [0, 0, 0])  # lost units, lost cents, events
    weeks: dict[date, list[int]] = defaultdict(lambda: [0, 0])
    for movement, value in events:
        moment = management_reports._aware(movement.created_at).date()
        week = moment - timedelta(days=moment.weekday())
        if value < 0:
            found += -value
            weeks[week][1] += -value
            continue
        lost += value
        weeks[week][0] += value
        product = products.get(movement.product_id)
        reason = REASON_LABELS.get(movement.reason_code or "", "Other adjustment")
        by_reason[reason] += value
        by_category[product.category if product else "Unknown"] += value
        by_store[stores.get(movement.store_id, "?")] += value
        slot = per_product[movement.product_id]
        slot[0] += -movement.quantity
        slot[1] += value
        slot[2] += 1

    sales_query = (
        select(Product.category, func.coalesce(func.sum(SaleItem.line_total_cents - SaleItem.tax_cents), 0))
        .join(Sale, Sale.id == SaleItem.sale_id)
        .join(Product, Product.id == SaleItem.product_id)
        .where(
            Sale.created_at >= since,
            Sale.created_at < until,
            Sale.is_quote_proforma.is_(False),
            Sale.status.in_(POSTED),
        )
        .group_by(Product.category)
    )
    if scope is not None:
        sales_query = sales_query.where(Sale.store_id == scope)
    category_sales = {category: int(cents) for category, cents in db.execute(sales_query)}
    net_sales = sum(category_sales.values())
    sold = _units(db, since, until, scope)
    net = lost - found
    store_bps = _share(net, net_sales)

    def slices(values: dict[str, int]) -> list[ShrinkSlice]:
        return [
            ShrinkSlice(label=label, lost_cents=cents, share_bps=_share(cents, lost))
            for label, cents in sorted(values.items(), key=lambda item: -item[1])
        ]

    top = []
    for product_id, (units, cents, count) in sorted(per_product.items(), key=lambda item: -item[1][1])[:15]:
        product = products.get(product_id)
        if product is None:
            continue
        sold_units = sold.get(product_id, 0)
        top.append(
            ShrinkProduct(
                product_id=product_id,
                sku=product.sku,
                name=product.name,
                category=product.category,
                sold_by_weight=product.sold_by_weight,
                lost_units=units,
                lost_cents=cents,
                events=count,
                sold_units=sold_units,
                shrink_rate_bps=_share(units, units + sold_units),
            )
        )
    hotspots = []
    for category, cents in sorted(by_category.items(), key=lambda item: -item[1]):
        rate = _share(cents, category_sales.get(category, 0)) if category_sales.get(category) else None
        if rate is None:
            if cents > 0:
                hotspots.append(
                    ShrinkHotspot(
                        category=category,
                        shrink_bps=0,
                        lost_cents=cents,
                        summary=f"{category}: {_money(cents, currency)} lost with no sales in the period.",
                    )
                )
            continue
        if rate >= max(2 * store_bps, BENCHMARK_BPS):
            hotspots.append(
                ShrinkHotspot(
                    category=category,
                    shrink_bps=rate,
                    lost_cents=cents,
                    summary=(
                        f"{category}: {rate / 100:.1f}% of its sales lost, against {store_bps / 100:.1f}% "
                        "for the store; check storage, rotation and shelf security."
                    ),
                )
            )
    return ShrinkReport(
        since=since,
        until=until,
        currency=currency,
        lost_cents=lost,
        found_cents=found,
        net_cents=net,
        net_sales_cents=net_sales,
        shrink_bps=store_bps,
        by_reason=slices(by_reason),
        by_category=slices(by_category),
        by_store=slices(by_store),
        top_products=top,
        weeks=[
            ShrinkWeek(week_start=week, lost_cents=values[0], found_cents=values[1])
            for week, values in sorted(weeks.items())
        ],
        hotspots=hotspots,
    )


# --- Feed --------------------------------------------------------------------------------------------------------


FEED_TTL_SECONDS = 600
_feed_cache: dict[tuple[object, ...], tuple[float, InsightFeed]] = {}


def feed(db: Session, principal: Principal) -> InsightFeed:
    """The header bell: the most urgent signals this user may see. Cached for ten minutes per business, branch
    and permission set, since every portal page asks for it."""
    bind = db.get_bind()
    key = (id(bind), str(bind.url), principal.store_id, principal.permissions)
    cached = _feed_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < FEED_TTL_SECONDS:
        return cached[1]
    result = _build_feed(db, principal)
    _feed_cache[key] = (time.monotonic(), result)
    return result


def _build_feed(db: Session, principal: Principal) -> InsightFeed:
    items: list[InsightItem] = []
    if principal.has(Permission.AUDIT_READ):
        report = anomalies(db, principal, days=30)
        for anomaly in report.anomalies[:4]:
            items.append(
                InsightItem(
                    kind="anomaly",
                    severity=anomaly.severity,
                    title="Cash drawer" if anomaly.kind.startswith("CASH") else "Unusual activity",
                    body=anomaly.summary,
                    to="/insights?tab=anomalies",
                )
            )
    if principal.has(Permission.PORTAL_REPORTS_READ):
        prices = pricing(db, principal, limit=200, include_clearance=False)
        expiring = prices.counts.get("EXPIRY_MARKDOWN", 0)
        under = prices.counts.get("RAISE_TO_FLOOR", 0)
        if expiring:
            items.append(
                InsightItem(
                    kind="pricing",
                    severity="HIGH",
                    title="Expiring stock",
                    body=f"{expiring} batch{'es' if expiring != 1 else ''} will expire before selling through; "
                    "mark them down.",
                    to="/insights?tab=pricing",
                )
            )
        if under:
            items.append(
                InsightItem(
                    kind="pricing",
                    severity="MEDIUM",
                    title="Selling under the margin floor",
                    body=f"{under} product{'s' if under != 1 else ''} sold recently below the minimum margin.",
                    to="/insights?tab=pricing",
                )
            )
        losses = shrink(db, principal, days=30)
        for hotspot in losses.hotspots[:2]:
            items.append(
                InsightItem(
                    kind="shrink",
                    severity="MEDIUM",
                    title="Shrink hotspot",
                    body=hotspot.summary,
                    to="/insights?tab=shrink",
                )
            )
    items.sort(key=lambda item: item.severity != "HIGH")
    return InsightFeed(items=items[:8])


def run_scan(db: Session) -> str:
    """Daily job: records the anomalies found over the last 30 days in the audit trail."""
    report = detect_anomalies(db, days=30, scope=None)
    if not report.anomalies:
        return "no anomalies"
    from app.services import audit

    audit.record(
        db,
        action_type="UPDATE",
        action="insights.anomaly_scan",
        target_entity="Insights",
        client_device="system",
        details={
            "high": sum(1 for item in report.anomalies if item.severity == "HIGH"),
            "medium": sum(1 for item in report.anomalies if item.severity == "MEDIUM"),
            "kinds": sorted({item.kind for item in report.anomalies}),
        },
    )
    db.commit()
    return f"{len(report.anomalies)} anomalies"
