"""Restaurant insights (statistical): kitchen prep-time prediction per station, table turnaround with predicted free
times, and upsell pairs ("guests who order X usually add Y") from basket co-occurrence. Every number comes from
kitchen tickets, open orders and sales; each prediction carries the evidence behind it."""

from __future__ import annotations

import heapq
import statistics
import time
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.deps import Principal
from app.core.errors import ApiError
from app.models.kitchen import KitchenStation, KitchenTicket
from app.models.product import Product
from app.models.restaurant import DiningArea, DiningTable, OpenOrder
from app.models.sale import Sale
from app.models.sale_item import SaleItem
from app.models.store import Store
from app.schemas.insights import (
    DurationSlice,
    KitchenReport,
    LiveTicket,
    OpenTable,
    PrepModel,
    StationInsight,
    TableReport,
    TableTurn,
    UpsellPair,
    UpsellReport,
)
from app.services.settings_service import cached_settings

POSTED = ("completed", "partially_refunded", "refunded")
# The business runs on UAE time (UTC+4, no daylight saving); day-parts and busy hours use it.
LOCAL_OFFSET = timedelta(hours=4)
HISTORY_DAYS = 28
MIN_MODEL_SAMPLES = 20
OPEN_TICKET = ("NEW", "PREPARING")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _minutes(start: datetime, end: datetime) -> float:
    return (_aware(end) - _aware(start)).total_seconds() / 60


def _scope(principal: Principal, store_id: uuid.UUID | None) -> uuid.UUID | None:
    if principal.store_id is not None:
        if store_id is not None and store_id != principal.store_id:
            raise ApiError(403, "store_scope", "You can only see your own store.")
        return principal.store_id
    return store_id


def _share(part: int, whole: int) -> int:
    return round(part * 10_000 / whole) if whole else 0


def _percentile(values: list[float], share: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * share))]


# --- Kitchen -----------------------------------------------------------------------------------------------------


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float] | None:
    """Gaussian elimination with partial pivoting for the 3x3 normal equations."""
    size = len(vector)
    rows = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda index: abs(rows[index][column]))
        if abs(rows[pivot][column]) < 1e-9:
            return None
        rows[column], rows[pivot] = rows[pivot], rows[column]
        for index in range(size):
            if index != column:
                factor = rows[index][column] / rows[column][column]
                rows[index] = [value - factor * base for value, base in zip(rows[index], rows[column], strict=True)]
    return [rows[index][size] / rows[index][index] for index in range(size)]


def fit_prep_model(samples: list[tuple[int, int, float]]) -> PrepModel | None:
    """Least squares on (items, queued, minutes). Negative slopes are dropped (they mean noise, not speed-ups)."""
    if len(samples) < MIN_MODEL_SAMPLES:
        return None
    xs = [(1.0, float(items), float(queued)) for items, queued, _ in samples]
    ys = [minutes for _, _, minutes in samples]
    normal = [[sum(row[a] * row[b] for row in xs) for b in range(3)] for a in range(3)]
    # A whisper of ridge on the slopes keeps the system solvable when a term never varies (e.g. no queue at all).
    for index in (1, 2):
        normal[index][index] += 1e-6 * len(samples)
    target = [sum(row[a] * y for row, y in zip(xs, ys, strict=True)) for a in range(3)]
    beta = _solve(normal, target)
    median = statistics.median(ys)
    if beta is None:
        beta = [median, 0.0, 0.0]
    base, per_item, per_queued = beta[0], max(0.0, beta[1]), max(0.0, beta[2])
    if per_item == 0.0 or per_queued == 0.0:
        # Refit the base with the kept slopes so the line still passes through the data.
        base = statistics.fmean(y - per_item * row[1] - per_queued * row[2] for row, y in zip(xs, ys, strict=True))
    base = max(0.5, base)

    def predict(items: float, queued: float) -> float:
        return base + per_item * items + per_queued * queued

    mae = statistics.fmean(abs(predict(row[1], row[2]) - y) for row, y in zip(xs, ys, strict=True))
    baseline = statistics.fmean(abs(median - y) for y in ys)
    return PrepModel(
        base_minutes=round(base, 2),
        per_item_minutes=round(per_item, 2),
        per_queued_minutes=round(per_queued, 2),
        samples=len(samples),
        mae_minutes=round(mae, 2),
        baseline_mae_minutes=round(baseline, 2),
    )


def _predict(model: PrepModel | None, fallback: float | None, items: float, queued: float) -> float | None:
    if model is not None:
        return model.base_minutes + model.per_item_minutes * items + model.per_queued_minutes * queued
    return fallback


def _items(ticket: KitchenTicket) -> int:
    return sum(item.quantity for item in ticket.items if item.voided_at is None) or 1


def kitchen(db: Session, principal: Principal, *, store_id: uuid.UUID | None = None) -> KitchenReport:
    scope = _scope(principal, store_id)
    now = _now()
    timers = cached_settings(db).module_settings.kds
    station_query = (
        select(KitchenStation, Store.code)
        .join(Store, Store.id == KitchenStation.store_id)
        .where(KitchenStation.is_active.is_(True))
    )
    if scope is not None:
        station_query = station_query.where(KitchenStation.store_id == scope)
    stations = list(db.execute(station_query.order_by(Store.code, KitchenStation.position, KitchenStation.name)))
    ticket_query = select(KitchenTicket).where(KitchenTicket.fired_at >= now - timedelta(days=HISTORY_DAYS))
    if scope is not None:
        ticket_query = ticket_query.where(KitchenTicket.store_id == scope)
    by_station: dict[uuid.UUID, list[KitchenTicket]] = defaultdict(list)
    for ticket in db.scalars(ticket_query):
        by_station[ticket.station_id].append(ticket)

    out: list[StationInsight] = []
    for station, store_code in stations:
        tickets = sorted(by_station.get(station.id, []), key=lambda row: _aware(row.fired_at))
        samples: list[tuple[int, int, float]] = []
        busy: Counter[int] = Counter()
        active: list[datetime] = []  # completion times of tickets fired earlier, as a min-heap
        queued_at: dict[uuid.UUID, int] = {}
        for ticket in tickets:
            fired = _aware(ticket.fired_at)
            while active and active[0] <= fired:
                heapq.heappop(active)
            queued_at[ticket.id] = len(active)
            done = ticket.ready_at or ticket.bumped_at
            heapq.heappush(active, _aware(done) if done is not None else datetime.max.replace(tzinfo=UTC))
            busy[(fired + LOCAL_OFFSET).hour] += 1
            if done is not None:
                minutes = _minutes(fired, done)
                if 0 <= minutes <= 240:
                    samples.append((_items(ticket), queued_at[ticket.id], minutes))
        durations = [minutes for _, _, minutes in samples]
        model = fit_prep_model(samples)
        median = statistics.median(durations) if durations else None
        live_tickets = [ticket for ticket in tickets if ticket.status in OPEN_TICKET]
        live = []
        for ticket in live_tickets:
            elapsed = _minutes(ticket.fired_at, now)
            predicted = _predict(model, median, _items(ticket), queued_at.get(ticket.id, 0))
            predicted = predicted if predicted is not None else float(timers.warn_minutes)
            live.append(
                LiveTicket(
                    ticket_id=ticket.id,
                    number=ticket.number,
                    label=ticket.label,
                    items=_items(ticket),
                    elapsed_minutes=round(elapsed, 1),
                    predicted_minutes=round(predicted, 1),
                    remaining_minutes=round(max(0.0, predicted - elapsed), 1),
                    at_risk=elapsed > timers.late_minutes or predicted > timers.late_minutes,
                )
            )
        typical_items = statistics.median([items for items, _, _ in samples]) if samples else 1
        wait_now = _predict(model, median, typical_items, len(live_tickets))
        out.append(
            StationInsight(
                station_id=station.id,
                station_name=station.name,
                store_code=store_code,
                tickets_28d=len(tickets),
                median_minutes=round(median, 1) if median is not None else None,
                p90_minutes=round(_percentile(durations, 0.9), 1) if durations else None,
                late_share_bps=_share(sum(1 for value in durations if value > timers.late_minutes), len(durations)),
                model=model,
                open_tickets=len(live_tickets),
                wait_now_minutes=round(wait_now, 1) if wait_now is not None else None,
                busiest_hours=[hour for hour, _ in busy.most_common(3)],
                live=sorted(live, key=lambda row: (not row.at_risk, -row.elapsed_minutes)),
            )
        )
    return KitchenReport(as_of=now, warn_minutes=timers.warn_minutes, late_minutes=timers.late_minutes, stations=out)


# --- Tables ------------------------------------------------------------------------------------------------------

DAYPARTS = (("Breakfast", 6, 11), ("Lunch", 11, 16), ("Dinner", 16, 23), ("Late", 23, 30))


def party(covers: int) -> str:
    if covers <= 2:
        return "1-2 guests"
    if covers <= 4:
        return "3-4 guests"
    return "5+ guests"


def daypart(moment: datetime) -> str:
    hour = (_aware(moment) + LOCAL_OFFSET).hour
    hour = hour + 24 if hour < 6 else hour
    return next(name for name, start, end in DAYPARTS if start <= hour < end)


def _slices(groups: dict[str, list[float]], order: list[str]) -> list[DurationSlice]:
    return [
        DurationSlice(
            label=label,
            orders=len(groups[label]),
            median_minutes=round(statistics.median(groups[label]), 1),
            p90_minutes=round(_percentile(groups[label], 0.9), 1),
        )
        for label in order
        if groups.get(label)
    ]


def tables(db: Session, principal: Principal, *, store_id: uuid.UUID | None = None, days: int = 28) -> TableReport:
    if not 7 <= days <= 365:
        raise ApiError(422, "validation_error", "Look back between 7 and 365 days.")
    scope = _scope(principal, store_id)
    now = _now()
    since = now - timedelta(days=days)
    table_query = (
        select(DiningTable, Store.code)
        .join(DiningArea, DiningArea.id == DiningTable.area_id)
        .join(Store, Store.id == DiningArea.store_id)
    )
    if scope is not None:
        table_query = table_query.where(DiningArea.store_id == scope)
    known = {table.id: (table, code) for table, code in db.execute(table_query)}
    orders_query = select(OpenOrder).where(
        OpenOrder.service_type == "DINE_IN",
        OpenOrder.table_id.is_not(None),
        OpenOrder.opened_at >= since,
    )
    if scope is not None:
        orders_query = orders_query.where(OpenOrder.store_id == scope)
    orders = list(db.scalars(orders_query))
    closed = [order for order in orders if order.status == "SETTLED" and order.closed_at is not None]
    durations = {order.id: _minutes(order.opened_at, order.closed_at) for order in closed}  # type: ignore[arg-type]
    durations = {key: value for key, value in durations.items() if 1 <= value <= 600}
    revenue: dict[uuid.UUID, int] = {}
    if durations:
        for order_id, cents in db.execute(
            select(Sale.order_id, func.coalesce(func.sum(Sale.total_cents), 0))
            .where(Sale.order_id.in_(durations.keys()), Sale.status.in_(POSTED))
            .group_by(Sale.order_id)
        ):
            revenue[order_id] = int(cents)
    by_party: dict[str, list[float]] = defaultdict(list)
    by_part: dict[str, list[float]] = defaultdict(list)
    by_party_part: dict[tuple[str, str], list[float]] = defaultdict(list)
    per_table: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for order in closed:
        minutes = durations.get(order.id)
        if minutes is None:
            continue
        size, part = party(order.covers), daypart(order.opened_at)
        by_party[size].append(minutes)
        by_part[part].append(minutes)
        by_party_part[(size, part)].append(minutes)
        assert order.table_id is not None
        per_table[order.table_id].append(order.id)
    overall = list(durations.values())

    def expected(covers: int, opened: datetime) -> tuple[float, float]:
        """(median, p90) for this party size and day-part, falling back to the party size, then everyone."""
        size = party(covers)
        for values in (by_party_part.get((size, daypart(opened))), by_party.get(size), overall):
            if values and len(values) >= 3:
                return statistics.median(values), _percentile(values, 0.9)
        return 60.0, 90.0

    opened_day = {order.id: (_aware(order.opened_at) + LOCAL_OFFSET).date() for order in closed}
    turns = []
    for table_id, order_ids in per_table.items():
        found = known.get(table_id)
        if found is None:
            continue
        table, code = found
        active_days = len({opened_day[oid] for oid in order_ids})
        minutes = [durations[oid] for oid in order_ids]
        cents = sum(revenue.get(oid, 0) for oid in order_ids)
        hours = sum(minutes) / 60
        turns.append(
            TableTurn(
                table_id=table_id,
                label=table.label,
                store_code=code,
                seats=table.seats,
                turns=len(order_ids),
                turns_per_day=round(len(order_ids) / max(active_days, 1), 1),
                median_minutes=round(statistics.median(minutes), 1),
                revenue_cents=cents,
                revenue_per_hour_cents=round(cents / hours) if hours else 0,
            )
        )
    open_tables = []
    for order in orders:
        if order.status != "OPEN" or order.table_id is None or order.table_id not in known:
            continue
        elapsed = _minutes(order.opened_at, now)
        median, p90 = expected(order.covers, order.opened_at)
        remaining = max(5.0, median - elapsed)
        open_tables.append(
            OpenTable(
                order_id=order.id,
                table_id=order.table_id,
                label=known[order.table_id][0].label,
                covers=order.covers,
                elapsed_minutes=round(elapsed, 1),
                expected_minutes=round(median, 1),
                predicted_free_at=now + timedelta(minutes=remaining),
                lingering=elapsed > p90,
            )
        )
    return TableReport(
        as_of=now,
        currency=cached_settings(db).currency,
        days=days,
        dine_in_orders=len(overall),
        median_minutes=round(statistics.median(overall), 1) if overall else None,
        by_party=_slices(by_party, ["1-2 guests", "3-4 guests", "5+ guests"]),
        by_daypart=_slices(by_part, [name for name, _, _ in DAYPARTS]),
        tables=sorted(turns, key=lambda row: -row.revenue_per_hour_cents),
        open_tables=sorted(open_tables, key=lambda row: row.predicted_free_at),
    )


# --- Upsell ------------------------------------------------------------------------------------------------------

UPSELL_DAYS = 90
MIN_TOGETHER = 5
MIN_CONFIDENCE_BPS = 1500
MIN_LIFT = 1.2
UPSELL_TTL_SECONDS = 1800
Rule = tuple[uuid.UUID, int, int, float]  # (add-on, baskets with both, confidence bps, lift)
Rules = dict[uuid.UUID, list[Rule]]
_upsell_cache: dict[tuple[object, ...], tuple[float, int, Rules]] = {}


def _baskets(db: Session, since: datetime, scope: uuid.UUID | None) -> dict[uuid.UUID, set[uuid.UUID]]:
    query = (
        select(SaleItem.sale_id, SaleItem.product_id)
        .join(Sale, Sale.id == SaleItem.sale_id)
        .where(Sale.created_at >= since, Sale.is_quote_proforma.is_(False), Sale.status.in_(POSTED))
    )
    if scope is not None:
        query = query.where(Sale.store_id == scope)
    baskets: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for sale_id, product_id in db.execute(query):
        baskets[sale_id].add(product_id)
    return baskets


def mine_pairs(
    baskets: list[set[uuid.UUID]],
) -> dict[uuid.UUID, list[tuple[uuid.UUID, int, int, float]]]:
    """For each product: (add-on, baskets with both, confidence in bps, lift), strongest first."""
    total = len(baskets)
    single: Counter[uuid.UUID] = Counter()
    pairs: Counter[tuple[uuid.UUID, uuid.UUID]] = Counter()
    for basket in baskets:
        items = sorted(basket)[:25]
        single.update(items)
        for index, first in enumerate(items):
            for second in items[index + 1 :]:
                pairs[(first, second)] += 1
    rules: dict[uuid.UUID, list[tuple[uuid.UUID, int, int, float]]] = defaultdict(list)
    for (first, second), together in pairs.items():
        if together < MIN_TOGETHER:
            continue
        for anchor, add_on in ((first, second), (second, first)):
            confidence = together / single[anchor]
            lift = confidence / (single[add_on] / total)
            if confidence * 10_000 >= MIN_CONFIDENCE_BPS and lift >= MIN_LIFT:
                rules[anchor].append((add_on, together, round(confidence * 10_000), round(lift, 2)))
    for anchor in rules:
        rules[anchor].sort(key=lambda rule: (-rule[2], -rule[1]))
    return rules


def _rules(db: Session, scope: uuid.UUID | None) -> tuple[int, Rules]:
    bind = db.get_bind()
    key = (id(bind), str(bind.url), scope)
    cached = _upsell_cache.get(key)
    if cached is not None and time.monotonic() - cached[0] < UPSELL_TTL_SECONDS:
        return cached[1], cached[2]
    # Single-item orders count too: they are the orders where the add-on was not taken.
    baskets = list(_baskets(db, _now() - timedelta(days=UPSELL_DAYS), scope).values())
    rules = mine_pairs(baskets)
    _upsell_cache[key] = (time.monotonic(), len(baskets), rules)
    return len(baskets), rules


def upsell(
    db: Session,
    principal: Principal,
    *,
    product_ids: list[uuid.UUID],
    store_id: uuid.UUID | None = None,
    limit: int = 20,
) -> UpsellReport:
    """With product_ids: add-ons for what is already on the order (the waiter's prompt). Without: the strongest
    pairs across the menu."""
    scope = _scope(principal, store_id)
    baskets, rules = _rules(db, scope)
    in_order = set(product_ids)
    candidates: list[tuple[uuid.UUID, tuple[uuid.UUID, int, int, float]]] = []
    if in_order:
        best: dict[uuid.UUID, tuple[uuid.UUID, tuple[uuid.UUID, int, int, float]]] = {}
        for anchor in in_order:
            for rule in rules.get(anchor, []):
                if rule[0] in in_order:
                    continue
                if rule[0] not in best or rule[2] > best[rule[0]][1][2]:
                    best[rule[0]] = (anchor, rule)
        candidates = sorted(best.values(), key=lambda item: -item[1][2])
    else:
        candidates = sorted(
            ((anchor, rule) for anchor, items in rules.items() for rule in items[:3]),
            key=lambda item: (-item[1][2], -item[1][1]),
        )
    candidates = candidates[:limit]
    wanted = {anchor for anchor, _ in candidates} | {rule[0] for _, rule in candidates}
    names = (
        {row.id: row for row in db.scalars(select(Product).where(Product.id.in_(wanted))).unique()} if wanted else {}
    )
    pairs = []
    for anchor, (add_on, together, confidence, lift) in candidates:
        product, extra = names.get(anchor), names.get(add_on)
        if product is None or extra is None:
            continue
        pairs.append(
            UpsellPair(
                product_id=anchor,
                product_name=product.name,
                add_on_id=add_on,
                add_on_name=extra.name,
                add_on_price_cents=extra.price_cents,
                together=together,
                confidence_bps=confidence,
                lift=lift,
                pitch=f"{round(confidence / 100)}% of guests who order {product.name} add {extra.name}.",
            )
        )
    return UpsellReport(
        as_of=_now(), currency=cached_settings(db).currency, days=UPSELL_DAYS, baskets=baskets, pairs=pairs
    )
