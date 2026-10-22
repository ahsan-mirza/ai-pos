from datetime import date, datetime
from typing import Literal
from uuid import UUID

from app.schemas.payloads import ApiModel

AnomalyKind = Literal["VOIDS", "NO_SALES", "REFUNDS", "PRICE_OVERRIDES", "CASH_SHORT", "CASH_OVER"]
Severity = Literal["HIGH", "MEDIUM"]
PriceAction = Literal["RAISE_TO_FLOOR", "RAISE_ON_DEMAND", "EXPIRY_MARKDOWN", "CLEARANCE"]


class StaffActivity(ApiModel):
    """What one cashier rang up in the window, with the loss-prevention signals beside it."""

    user_id: UUID
    user_name: str
    sales: int
    voids: int
    no_sales: int
    refunds: int
    refund_cents: int
    price_overrides: int
    shifts_closed: int
    cash_short_cents: int
    cash_over_cents: int


class Anomaly(ApiModel):
    kind: AnomalyKind
    severity: Severity
    user_id: UUID
    user_name: str
    count: int
    sales: int
    # Events per 100 sales for this cashier and the median of their peers (rate signals only).
    rate: float | None
    peer_rate: float | None
    # Robust z-score against peers (median / MAD), or None for rule-based cash signals.
    score: float | None
    amount_cents: int | None
    summary: str


class AnomalyReport(ApiModel):
    as_of: datetime
    days: int
    currency: str
    peers: int
    staff: list[StaffActivity]
    anomalies: list[Anomaly]


class PriceSuggestion(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    store_code: str | None
    action: PriceAction
    price_cents: int
    suggested_price_cents: int
    change_pct: int
    reason: str
    units_28d: int
    on_hand: int
    cover_days: int | None
    expiry_date: date | None
    sold_by_weight: bool


class PricingReport(ApiModel):
    as_of: datetime
    currency: str
    counts: dict[str, int]
    suggestions: list[PriceSuggestion]


class ShrinkSlice(ApiModel):
    label: str
    lost_cents: int
    share_bps: int


class ShrinkProduct(ApiModel):
    product_id: UUID
    sku: str
    name: str
    category: str
    sold_by_weight: bool
    lost_units: int
    lost_cents: int
    events: int
    sold_units: int
    # Lost units as a share of lost + sold units: how much of what left the shelf was never paid for.
    shrink_rate_bps: int


class ShrinkWeek(ApiModel):
    week_start: date
    lost_cents: int
    found_cents: int


class ShrinkHotspot(ApiModel):
    category: str
    shrink_bps: int
    lost_cents: int
    summary: str


class ShrinkReport(ApiModel):
    since: datetime
    until: datetime
    currency: str
    lost_cents: int
    found_cents: int
    net_cents: int
    net_sales_cents: int
    # Net shrink as a share of net sales (retail benchmark: about 1.5%).
    shrink_bps: int
    by_reason: list[ShrinkSlice]
    by_category: list[ShrinkSlice]
    by_store: list[ShrinkSlice]
    top_products: list[ShrinkProduct]
    weeks: list[ShrinkWeek]
    hotspots: list[ShrinkHotspot]


class PrepModel(ApiModel):
    """Prep minutes ~ base + per_item x items + per_queued x tickets already open at the station when fired."""

    base_minutes: float
    per_item_minutes: float
    per_queued_minutes: float
    samples: int
    # Mean absolute error of the model, and of always guessing the median, over the same tickets.
    mae_minutes: float
    baseline_mae_minutes: float


class LiveTicket(ApiModel):
    ticket_id: UUID
    number: int
    label: str
    items: int
    elapsed_minutes: float
    predicted_minutes: float
    remaining_minutes: float
    at_risk: bool


class StationInsight(ApiModel):
    station_id: UUID
    station_name: str
    store_code: str
    tickets_28d: int
    median_minutes: float | None
    p90_minutes: float | None
    late_share_bps: int
    model: PrepModel | None
    open_tickets: int
    # Expected prep time of a typical ticket fired now, given the current queue.
    wait_now_minutes: float | None
    busiest_hours: list[int]
    live: list[LiveTicket]


class KitchenReport(ApiModel):
    as_of: datetime
    warn_minutes: int
    late_minutes: int
    stations: list[StationInsight]


class TableTurn(ApiModel):
    table_id: UUID
    label: str
    store_code: str
    seats: int
    turns: int
    turns_per_day: float
    median_minutes: float | None
    revenue_cents: int
    revenue_per_hour_cents: int


class OpenTable(ApiModel):
    order_id: UUID
    table_id: UUID
    label: str
    covers: int
    elapsed_minutes: float
    expected_minutes: float
    predicted_free_at: datetime
    lingering: bool


class DurationSlice(ApiModel):
    label: str
    orders: int
    median_minutes: float
    p90_minutes: float


class TableReport(ApiModel):
    as_of: datetime
    currency: str
    days: int
    dine_in_orders: int
    median_minutes: float | None
    by_party: list[DurationSlice]
    by_daypart: list[DurationSlice]
    tables: list[TableTurn]
    open_tables: list[OpenTable]


class UpsellPair(ApiModel):
    product_id: UUID
    product_name: str
    add_on_id: UUID
    add_on_name: str
    add_on_price_cents: int
    together: int
    # Share of baskets with the product that also had the add-on, and how much likelier that is than chance.
    confidence_bps: int
    lift: float
    pitch: str


class UpsellReport(ApiModel):
    as_of: datetime
    currency: str
    days: int
    baskets: int
    pairs: list[UpsellPair]


class InsightItem(ApiModel):
    kind: Literal["anomaly", "pricing", "shrink"]
    severity: Severity
    title: str
    body: str
    to: str


class InsightFeed(ApiModel):
    items: list[InsightItem]
