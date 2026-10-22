import type { AnalyticsTimeframe, PaymentMethod } from "./enums.js";

export interface CategorySlice {
  category: string;
  units: number;
  revenue_cents: number;
}

export interface PaymentSplit {
  method: PaymentMethod;
  revenue_cents: number;
}

export interface AnalyticsSummary {
  timeframe: AnalyticsTimeframe;
  currency: string;
  net_revenue_cents: number;
  units_sold: number;
  average_ticket_cents: number;
  units_growth_bps: number | null;
  revenue_series: number[];
  categories: CategorySlice[];
  payment_split: PaymentSplit[];
  wholesale_revenue_cents?: number;
  retail_revenue_cents?: number;
  /** Unpaid on-account balances across all customers. */
  receivables_cents?: number;
  /** FIFO cost of the units sold (estimated for unbatched stock). */
  cogs_cents?: number;
  gross_margin_cents?: number;
}
