/** AI insights: loss-prevention anomalies, price suggestions and shrink analytics (GET /api/v1/insights/*). */

export type AnomalyKind = "VOIDS" | "NO_SALES" | "REFUNDS" | "PRICE_OVERRIDES" | "CASH_SHORT" | "CASH_OVER";
export type InsightSeverity = "HIGH" | "MEDIUM";
export type PriceAction = "RAISE_TO_FLOOR" | "RAISE_ON_DEMAND" | "EXPIRY_MARKDOWN" | "CLEARANCE";

export const ANOMALY_LABELS: Record<AnomalyKind, string> = {
  VOIDS: "Voided items",
  NO_SALES: "No-sale drawer opens",
  REFUNDS: "Refunds",
  PRICE_OVERRIDES: "Price overrides",
  CASH_SHORT: "Drawer short",
  CASH_OVER: "Drawer over",
};

export const PRICE_ACTION_LABELS: Record<PriceAction, string> = {
  RAISE_TO_FLOOR: "Below margin floor",
  RAISE_ON_DEMAND: "Demand outrunning stock",
  EXPIRY_MARKDOWN: "Expiring soon",
  CLEARANCE: "Clearance",
};

export interface StaffActivity {
  user_id: string;
  user_name: string;
  sales: number;
  voids: number;
  no_sales: number;
  refunds: number;
  refund_cents: number;
  price_overrides: number;
  shifts_closed: number;
  cash_short_cents: number;
  cash_over_cents: number;
}

export interface Anomaly {
  kind: AnomalyKind;
  severity: InsightSeverity;
  user_id: string;
  user_name: string;
  count: number;
  sales: number;
  /** Events per 100 sales, and the median of the cashier's peers. */
  rate: number | null;
  peer_rate: number | null;
  /** Robust z-score against peers; null for rule-based cash signals. */
  score: number | null;
  amount_cents: number | null;
  summary: string;
}

export interface AnomalyReport {
  as_of: string;
  days: number;
  currency: string;
  peers: number;
  staff: StaffActivity[];
  anomalies: Anomaly[];
}

export interface PriceSuggestion {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  store_code: string | null;
  action: PriceAction;
  price_cents: number;
  suggested_price_cents: number;
  change_pct: number;
  reason: string;
  units_28d: number;
  on_hand: number;
  cover_days: number | null;
  expiry_date: string | null;
  sold_by_weight: boolean;
}

export interface PricingReport {
  as_of: string;
  currency: string;
  counts: Partial<Record<PriceAction, number>>;
  suggestions: PriceSuggestion[];
}

export interface ShrinkSlice {
  label: string;
  lost_cents: number;
  share_bps: number;
}

export interface ShrinkProduct {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  sold_by_weight: boolean;
  lost_units: number;
  lost_cents: number;
  events: number;
  sold_units: number;
  shrink_rate_bps: number;
}

export interface ShrinkReport {
  since: string;
  until: string;
  currency: string;
  lost_cents: number;
  found_cents: number;
  net_cents: number;
  net_sales_cents: number;
  shrink_bps: number;
  by_reason: ShrinkSlice[];
  by_category: ShrinkSlice[];
  by_store: ShrinkSlice[];
  top_products: ShrinkProduct[];
  weeks: { week_start: string; lost_cents: number; found_cents: number }[];
  hotspots: { category: string; shrink_bps: number; lost_cents: number; summary: string }[];
}

/** Prep minutes ~ base + per_item x items + per_queued x tickets already open when fired. */
export interface PrepModel {
  base_minutes: number;
  per_item_minutes: number;
  per_queued_minutes: number;
  samples: number;
  mae_minutes: number;
  baseline_mae_minutes: number;
}

export interface StationInsight {
  station_id: string;
  station_name: string;
  store_code: string;
  tickets_28d: number;
  median_minutes: number | null;
  p90_minutes: number | null;
  late_share_bps: number;
  model: PrepModel | null;
  open_tickets: number;
  wait_now_minutes: number | null;
  busiest_hours: number[];
  live: {
    ticket_id: string;
    number: number;
    label: string;
    items: number;
    elapsed_minutes: number;
    predicted_minutes: number;
    remaining_minutes: number;
    at_risk: boolean;
  }[];
}

export interface KitchenReport {
  as_of: string;
  warn_minutes: number;
  late_minutes: number;
  stations: StationInsight[];
}

export interface DurationSlice {
  label: string;
  orders: number;
  median_minutes: number;
  p90_minutes: number;
}

export interface TableReport {
  as_of: string;
  currency: string;
  days: number;
  dine_in_orders: number;
  median_minutes: number | null;
  by_party: DurationSlice[];
  by_daypart: DurationSlice[];
  tables: {
    table_id: string;
    label: string;
    store_code: string;
    seats: number;
    turns: number;
    turns_per_day: number;
    median_minutes: number | null;
    revenue_cents: number;
    revenue_per_hour_cents: number;
  }[];
  open_tables: {
    order_id: string;
    table_id: string;
    label: string;
    covers: number;
    elapsed_minutes: number;
    expected_minutes: number;
    predicted_free_at: string;
    lingering: boolean;
  }[];
}

export interface UpsellPair {
  product_id: string;
  product_name: string;
  add_on_id: string;
  add_on_name: string;
  add_on_price_cents: number;
  together: number;
  confidence_bps: number;
  lift: number;
  pitch: string;
}

export interface UpsellReport {
  as_of: string;
  currency: string;
  days: number;
  baskets: number;
  pairs: UpsellPair[];
}

export interface InsightItem {
  kind: "anomaly" | "pricing" | "shrink" | "kitchen";
  severity: InsightSeverity;
  title: string;
  body: string;
  to: string;
}
