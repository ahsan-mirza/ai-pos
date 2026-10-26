export interface PnlRow {
  month: string;
  store_id: string | null;
  store_code: string;
  net_sales_cents: number;
  returns_cents: number;
  revenue_cents: number;
  cogs_cents: number;
  gross_profit_cents: number;
  gross_margin_bps: number;
  expenses: Record<string, number>;
  other_purchases_cents: number;
  shrinkage_cents: number;
  operating_expenses_cents: number;
  operating_profit_cents: number;
}

export interface PnlReport {
  period_from: string;
  period_to: string;
  currency: string;
  rows: PnlRow[];
  by_store: PnlRow[];
  total: PnlRow;
  cost_estimated: boolean;
}

export interface ValuationRow {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  store_id: string;
  store_code: string;
  on_hand: number;
  unit_cost_cents: number;
  cost_value_cents: number;
  retail_value_cents: number;
  estimated: boolean;
}

export interface ValuationGroup {
  key: string;
  units: number;
  cost_value_cents: number;
  retail_value_cents: number;
}

export interface ValuationReport {
  as_of: string;
  currency: string;
  units: number;
  cost_value_cents: number;
  retail_value_cents: number;
  estimated_units: number;
  by_store: ValuationGroup[];
  by_category: ValuationGroup[];
  rows: ValuationRow[];
}

export interface AgedStockRow {
  product_id: string;
  sku: string;
  name: string;
  category: string;
  store_id: string;
  store_code: string;
  on_hand: number;
  cost_value_cents: number;
  last_sold_at: string | null;
  /** Whole UTC days since the last qualifying sale. Null when there has never been one. */
  days_since_sale: number | null;
  units_sold_90d: number;
  cover_days: number | null;
  status: "SLOW" | "DEAD";
  suggestion: string;
  reason?: string;
  brand?: string | null;
  sold_by_weight?: boolean;
  /** Whole UTC days since the first receipt. Null when that date is unknown. */
  days_in_stock?: number | null;
  /** Carrying cost at the report's annual rate. */
  holding_cost_month_cents?: number;
  holding_cost_to_date_cents?: number;
  price_cents?: number;
  /** Clearance price that respects the margin floor (or cost); null when already at the floor, cost is missing, or the stock is supplier-owned. */
  suggested_price_cents?: number | null;
  markdown_pct?: number;
  target_markdown_pct?: number;
  floor_cents?: number | null;
  expected_margin_bps?: number | null;
  cost_estimated?: boolean;
  review_required?: boolean;
  /** The target markdown could not be applied in full because of cost or the margin floor. */
  discount_limited?: boolean;
}

export interface AgedStockReport {
  as_of: string;
  currency: string;
  slow_days: number;
  dead_days: number;
  slow_value_cents: number;
  dead_value_cents: number;
  carrying_rate_bps?: number;
  holding_cost_month_cents?: number;
  holding_cost_to_date_cents?: number;
  /** Rows matching the filters, before the page slice. */
  total?: number;
  rows: AgedStockRow[];
}

export interface StaffSalesRow {
  user_id: string;
  name: string;
  sales: number;
  units: number;
  revenue_cents: number;
  cogs_cents: number;
  gross_profit_cents: number;
  gross_margin_bps: number;
  average_basket_cents: number;
  promotion_discount_cents: number;
  override_discount_cents: number;
  returns: number;
  returns_cents: number;
}

export interface StaffSalesReport {
  period_from: string;
  period_to: string;
  currency: string;
  rows: StaffSalesRow[];
}

/** Cashier discounts one staff member gave for one reason. */
export interface DiscountRow {
  user_id: string;
  name: string;
  reason: string;
  reason_label: string;
  lines: number;
  discount_cents: number;
  /** Lines a manager approved because the discount was above the cashier's limit. */
  approved_lines: number;
  share_bps: number;
}

export interface DiscountReport {
  period_from: string;
  period_to: string;
  currency: string;
  total_cents: number;
  rows: DiscountRow[];
  by_reason: { reason: string; reason_label: string; lines: number; discount_cents: number }[];
}
