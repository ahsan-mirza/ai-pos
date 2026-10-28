export interface AddonSearchFields {
  name: string;
  description: string;
  sort_order?: number;
}

function searchText(value: string): string {
  return value.toLocaleLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Rank an add-on against a search box. A higher score is a closer match on the name, then the description.
 * Zero means a word in the query is missing from both. An empty query matches every add-on equally.
 */
export function addonSearchScore(addon: AddonSearchFields, query: string): number {
  const needle = searchText(query);
  if (needle === "") return 1;
  const name = searchText(addon.name);
  const description = searchText(addon.description);
  const words = needle.split(" ").filter((word) => word.length > 0);
  const haystack = `${name} ${description}`;
  if (words.some((word) => !haystack.includes(word))) return 0;
  let score = 0;
  if (name === needle) score += 1000;
  else if (name.startsWith(needle)) score += 800;
  else if (name.includes(needle)) score += 600;
  if (description.includes(needle)) score += 80;
  const nameWords = name.split(" ");
  for (const word of words) {
    if (nameWords.some((part) => part === word)) score += 220;
    else if (nameWords.some((part) => part.startsWith(word))) score += 180;
    else if (name.includes(word)) score += 100;
    if (description.includes(word)) score += 40;
  }
  return score;
}

/** Matching add-ons, closest name first. Equal scores keep the catalogue order, then the name. */
export function rankAddons<T extends AddonSearchFields>(addons: readonly T[], query: string): T[] {
  return addons
    .map((addon) => ({ addon, score: addonSearchScore(addon, query) }))
    .filter((row) => row.score > 0)
    .sort((left, right) => {
      if (right.score !== left.score) return right.score - left.score;
      const order = (left.addon.sort_order ?? 0) - (right.addon.sort_order ?? 0);
      if (order !== 0) return order;
      return searchText(left.addon.name).localeCompare(searchText(right.addon.name));
    })
    .map((row) => row.addon);
}

/** Recurring price for one quantity over a whole billing cycle. Matches the API integer division. */
export function cycleAmountFils(monthlyFils: number, months: number, discountBps: number): number {
  if (months < 1 || discountBps < 0 || discountBps > 10_000 || monthlyFils < 0 || !Number.isFinite(monthlyFils)) return 0;
  return Math.floor((monthlyFils * months * (10_000 - discountBps)) / 10_000);
}

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
  module_keys: string[];
  sort_order: number;
}

export interface ModuleCatalogueItem {
  key: string;
  label: string;
  available: boolean;
  requires: string[];
  business_types: string[];
  preset_for: string[];
  plan_codes: string[];
  addon_codes: string[];
}

export interface BusinessTypeModules {
  key: string;
  label: string;
  preset: string[];
  eligible: string[];
}

export interface ModuleSummary {
  catalogue_total: number;
  implemented: number;
  not_implemented: number;
  active_addons: number;
  mapped_addons: number;
  active_subscriptions: number;
  trialing_subscriptions: number;
  past_due_subscriptions: number;
  canceled_subscriptions: number;
  pending_payments: number;
  addon_mrr_fils: number;
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
