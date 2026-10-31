export interface AddonSearchFields {
  name: string;
  description: string;
  sort_order?: number;
  /** Benefits, tags, and features. Empty when the caller only has the short description. */
  search_text?: string;
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
  const extra = searchText(addon.search_text ?? "");
  const words = needle.split(" ").filter((word) => word.length > 0);
  const haystack = `${name} ${description} ${extra}`;
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
    if (extra.includes(word)) score += 30;
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

export interface AddonBenefit {
  title: string;
  description: string;
}

export interface AddonFaq {
  question: string;
  answer: string;
}

export interface AddonListing {
  short_description: string;
  overview: string;
  category: string;
  tags: string[];
  benefits: AddonBenefit[];
  features: AddonBenefit[];
  steps: AddonBenefit[];
  requirements: string[];
  faqs: AddonFaq[];
  documentation_url: string;
  video_url: string;
  support: string;
  icon: string;
  image_url: string;
  featured: boolean;
  publication: "published" | "draft" | "archived";
}

export interface AddonPricePoint {
  monthly_fils: number;
  one_time_fils: number;
  refundable: boolean;
  effective_at: string;
  reason: string;
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
  listing?: AddonListing;
  price_history?: AddonPricePoint[];
  updated_at?: string;
}

export type MarketplaceState =
  | "included"
  | "available"
  | "activated"
  | "pending_payment"
  | "pending_activation"
  | "expired"
  | "unavailable"
  | "unpriced";

export interface MarketplaceItem {
  addon: BillingAddon;
  state: MarketplaceState;
  reason: string;
  invoice_id: string | null;
  compatible_labels: string[];
  search_text: string;
}

export interface MarketplaceCatalog {
  currency: string;
  available: number;
  activated: number;
  pending: number;
  recurring_fils: number;
  items: MarketplaceItem[];
}

export type MarketplaceSort = "recommended" | "name" | "price_asc" | "price_desc" | "recent";

/** Client-side view of a catalogue the server already scoped to this store. */
export function filterMarketplace(
  items: readonly MarketplaceItem[],
  query: string,
  state: string,
  category: string,
  pricing: string,
  sort: MarketplaceSort,
): MarketplaceItem[] {
  const rows = items.filter((item) => {
    if (state === "available" && item.state !== "available" && item.state !== "unpriced") return false;
    if (state !== "" && state !== "available" && item.state !== state) return false;
    if (category !== "" && (item.addon.listing?.category ?? "") !== category) return false;
    if (pricing === "monthly" && item.addon.monthly_fils <= 0) return false;
    if (pricing === "once" && item.addon.one_time_fils <= 0) return false;
    if (pricing === "deposit" && !item.addon.refundable) return false;
    if (pricing === "unpriced" && item.state !== "unpriced") return false;
    const score = addonSearchScore(
      {
        name: item.addon.name,
        description: item.addon.description,
        search_text: `${item.search_text} ${item.addon.listing?.short_description ?? ""}`,
        sort_order: item.addon.sort_order,
      },
      query,
    );
    return score > 0;
  });
  const price = (item: MarketplaceItem) => item.addon.monthly_fils || item.addon.one_time_fils;
  rows.sort((left, right) => {
    if (sort === "name") return left.addon.name.localeCompare(right.addon.name);
    if (sort === "price_asc") return price(left) - price(right);
    if (sort === "price_desc") return price(right) - price(left);
    if (sort === "recent") return (right.addon.updated_at ?? "").localeCompare(left.addon.updated_at ?? "");
    const featured = Number(right.addon.listing?.featured ?? false) - Number(left.addon.listing?.featured ?? false);
    if (featured !== 0) return featured;
    return left.addon.sort_order - right.addon.sort_order;
  });
  return rows;
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
