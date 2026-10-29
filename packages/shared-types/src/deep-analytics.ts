export interface DeepKpi {
  key: string;
  label: string;
  definition: string;
  formula: string;
  cents: number | null;
  count: number | null;
  bps: number | null;
  quality: "exact" | "estimated" | "unavailable";
  note: string | null;
}

export interface DeepTrendPoint {
  day: string;
  revenue_cents: number;
  gross_profit_cents: number;
}

export interface DeepHourPoint {
  hour: number;
  revenue_cents: number;
}

export interface DeepNamedAmount {
  name: string;
  cents: number;
}

export interface DeepSection {
  id: string;
  label: string;
  status: "available" | "unavailable";
  detail: string;
  cents: number | null;
}

export interface DeepForecast {
  status: "insufficient_history" | "estimated";
  horizon_days: number;
  method: string;
  daily_revenue_cents: number | null;
  note: string;
}

export interface DeepComparison {
  period_from: string;
  period_to: string;
  revenue_cents: number;
  gross_profit_cents: number;
  transactions: number;
  revenue_growth_bps: number | null;
  profit_growth_bps: number | null;
}

export interface DeepOverview {
  currency: string;
  period_from: string;
  period_to: string;
  generated_at: string;
  coverage: string;
  cost_estimated: boolean;
  kpis: DeepKpi[];
  comparison: DeepComparison | null;
  trend: DeepTrendPoint[];
  hourly: DeepHourPoint[];
  hourly_note: string | null;
  categories: DeepNamedAmount[];
  products: DeepNamedAmount[];
  slow_products: DeepNamedAmount[];
  payments: DeepNamedAmount[];
  cashiers: DeepNamedAmount[];
  branches: DeepNamedAmount[];
  payments_note: string;
  sections: DeepSection[];
  forecast: DeepForecast;
}
