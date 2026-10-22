export interface ReplenishmentSuggestion {
  id: string;
  product_id: string;
  product_name: string;
  sku: string;
  /** PURCHASE from a supplier, or TRANSFER from a branch or warehouse with surplus. */
  source: "PURCHASE" | "TRANSFER";
  supplier_id: string | null;
  supplier_name: string | null;
  from_store_code: string | null;
  on_hand: number;
  on_order: number;
  /** Forecast units per day, seasonal uplift included. */
  daily_rate: number;
  lead_time_days: number;
  forecast_units: number;
  safety_stock: number;
  suggested_qty: number;
  unit_cost_cents: number;
  seasonal_note: string | null;
  /** How supplier terms shaped the order, e.g. "MOQ 50 · cases of 12 · next order day Wed (+2d)". */
  terms_note?: string | null;
  /** Forecast method picked by backtest: weighted_average, trend, weekly or trend_weekly. */
  forecast_method?: string | null;
  forecast_method_label?: string | null;
  /** 0-1 accuracy over the last 28 days (1 - WAPE); null with too little history to test. */
  forecast_accuracy?: number | null;
  /** Trend as % change per week; set for trend methods. */
  trend_pct_week?: number | null;
  status: "PENDING" | "ACCEPTED" | "DISMISSED";
  purchase_order_id: string | null;
  transfer_id: string | null;
}

export interface ReplenishmentRun {
  id: string;
  store_id: string;
  store_code: string;
  review_days: number;
  created_at: string;
  purchase_value_cents: number;
  suggestions: ReplenishmentSuggestion[];
}

export interface ReplenishmentAcceptResult {
  purchase_order_ids: string[];
  transfer_ids: string[];
  run: ReplenishmentRun;
}

export interface SeasonalEvent {
  id: string;
  name: string;
  starts_on: string;
  ends_on: string;
  /** 13000 = demand at 130% of normal. */
  uplift_bps: number;
  category_id: string | null;
  is_active: boolean;
}

export type Weekday = "MON" | "TUE" | "WED" | "THU" | "FRI" | "SAT" | "SUN";

export interface SupplierLeadTime {
  id: string;
  name: string;
  code: string;
  lead_time_days: number;
  moq: number;
  pack_size: number;
  /** Days the supplier takes orders; empty means any day. */
  order_days: Weekday[];
}
