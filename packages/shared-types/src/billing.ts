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

export interface HardwareItem {
  id: string;
  sku: string;
  name: string;
  category_id: string;
  category_name: string;
  description: string;
  image_url: string | null;
  manufacturer: string;
  model: string;
  lease_available: boolean;
  purchase_available: boolean;
  monthly_fils: number;
  deposit_fils: number;
  fee_fils: number;
  purchase_fils: number | null;
  delivery_fils: number;
  currency: string;
  min_qty: number;
  max_qty: number;
  stock_qty: number | null;
  counts_as_register: boolean;
  compatibility: string;
  active: boolean;
  archived: boolean;
  available: boolean;
  internal_notes?: string;
}

export interface HardwarePick {
  item_id: string;
  quantity: number;
  mode: "lease" | "purchase";
  store_id?: string | null;
  store_label?: string;
}

export interface BillingCatalog {
  plans: BillingPlan[];
  cycles: BillingCycle[];
  addons: BillingAddon[];
  fees: BillingFee[];
  hardware?: HardwareItem[];
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
  hardware_monthly_fils?: number;
  deposit_fils?: number;
}

export interface BillingCheckout {
  checkout_id: string;
  mode: "simulator" | "stripe" | "transfer";
  url: string | null;
  quote: BillingQuote;
  bank?: Record<string, string> | null;
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

export interface PlanRevenue {
  plan_code: string;
  plan_name: string;
  paying_tenants: number;
  mrr_fils: number;
}

export interface StatusCount {
  status: string;
  tenants: number;
}

/** Control-plane figures. MRR excludes trials, deposits, and one-time fees. */
export interface ConsoleOverview {
  currency: string;
  tenants: number;
  active_tenants: number;
  suspended_tenants: number;
  practice_tenants: number;
  new_tenants_30d: number;
  stores: number;
  registers: number;
  paying_subscriptions: number;
  trialing: number;
  trials_ending_14d: number;
  past_due: number;
  canceled: number;
  mrr_fils: number;
  arr_fils: number;
  unpaid_checkouts_fils: number;
  unpaid_checkouts: number;
  open_change_requests: number;
  by_status: StatusCount[];
  by_plan: PlanRevenue[];
  definitions: string[];
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
