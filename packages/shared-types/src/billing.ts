export interface BillingPlan {
  id: string;
  code: string;
  name: string;
  included_registers: number;
  included_modules: string[];
  monthly_fils: number;
  trial_days: number;
  active: boolean;
  sort_order: number;
}

export interface BillingCycle {
  id: string;
  code: string;
  name: string;
  months: number;
  discount_bps: number;
  active: boolean;
  sort_order: number;
}

export interface BillingAddon {
  id: string;
  code: string;
  name: string;
  description: string;
  monthly_fils: number;
  one_time_fils: number;
  refundable: boolean;
  active: boolean;
  sort_order: number;
}

export interface BillingFee {
  id: string;
  code: string;
  name: string;
  amount_fils: number;
  active: boolean;
}

export interface BillingCatalog {
  plans: BillingPlan[];
  cycles: BillingCycle[];
  addons: BillingAddon[];
  fees: BillingFee[];
}

export interface QuoteLine {
  code: string;
  label: string;
  quantity: number;
  unit_fils: number;
  amount_fils: number;
  recurring: boolean;
  refundable: boolean;
}

export interface BillingQuote {
  currency: string;
  plan_code: string;
  plan_name: string;
  cycle_code: string;
  cycle_name: string;
  months: number;
  discount_bps: number;
  included_registers: number;
  lines: QuoteLine[];
  recurring_fils: number;
  one_time_fils: number;
  total_fils: number;
}

export interface BillingCheckout {
  checkout_id: string;
  mode: "simulator" | "stripe";
  url: string | null;
  quote: BillingQuote;
}

export interface BillingCheckoutStatus {
  checkout_id: string;
  status: "pending" | "paid" | "failed";
  error: string | null;
  result: {
    live_at?: string;
    mode?: string;
    opening_stock?: string;
    sales_removed?: number;
    sample_products_removed?: number;
    sample_customers_removed?: number;
  } | null;
}

export interface StoreSubscription {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  plan_code: string;
  plan_name: string;
  cycle_code: string;
  cycle_name: string;
  status: "trialing" | "active" | "past_due" | "canceled";
  trial_ends_at: string | null;
  current_period_end: string | null;
  practice_mode: boolean;
  next_recurring_fils: number;
  addons: { code: string; quantity: number }[];
}
