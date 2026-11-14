import { CAPABILITIES, type BillingPlan, type BillingQuote, type MarketplaceItem } from "@ai-pos/shared-types";
import { comparableFeature, isCustomPlan, isFreePlan } from "../subscriptionPlans";

/** A comparison row. Structural type so this module does not import the feature-access screen. */
export interface ComparableFeature {
  feature_key: string;
  label: string;
  state: string;
  plugin_code: string | null;
  description?: string;
  plugin_name?: string | null;
  /** Included for this business type because no published plan claims it. */
  baseline?: boolean;
  /** Open on the tenant's legacy plan even though the plan row does not name it. */
  grandfathered?: boolean;
}

export type PriceCadence = "amount" | "cycle" | "month" | "once" | "deposit";

export interface PriceLine {
  fils: number;
  currency: string;
  cadence: PriceCadence;
  /** Cycle name from the quote. Translated at render time. */
  periodName?: string;
}

export type PriceView =
  | { kind: "unpriced" }
  | { kind: "custom" }
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "none" }
  | { kind: "priced"; lines: PriceLine[]; discountBps: number | null };

const USAGE_ORDER = [
  ["branches", "Branches"],
  ["registers", "Registers"],
  ["staff", "Staff"],
  ["products", "Products"],
  ["customers", "Customers"],
] as const;

export type UsageMetricState = "known" | "unlimited" | "unconfigured" | "unavailable" | "zero";
export type UsageTone = "neutral" | "warning" | "limit";

export interface UsageMetricView {
  key: (typeof USAGE_ORDER)[number][0];
  label: string;
  state: UsageMetricState;
  used: number | null;
  limit: number | null;
  tone?: UsageTone;
  exceeded?: boolean;
}

export type UsageApiStatus = "available" | "near_limit" | "limit_reached" | "unlimited" | "unconfigured" | "unavailable";

export interface UsageMetricPayload {
  label: string;
  used: number | null;
  limit: number | null;
  available: number | null;
  percentage: number | null;
  status: UsageApiStatus;
  usage_available: boolean;
  exceeded: boolean;
}

export interface UsagePayload {
  plan_code: string | null;
  measured_at: string;
  metrics: Partial<Record<string, UsageMetricPayload>>;
}

export type AddonNextStep =
  | { type: "purchase" }
  | { type: "link"; href: string; label: "Open" | "View invoice" | "Review subscription" }
  | { type: "text"; label: string; translate: boolean };

/**
 * Discount shown beside the billing-period control.
 * Annual new-catalog invoices use the published policy rate. The amount on the card is still the quote.
 */
export function selectorDiscountBps(
  cycle: { code: string; discount_bps: number },
  annualDiscountBps: number | null | undefined,
): number {
  if (cycle.code === "ANNUAL" && annualDiscountBps != null && annualDiscountBps > 0) return annualDiscountBps;
  return cycle.discount_bps;
}

export function planPriceView(input: {
  plan: BillingPlan;
  quote?: BillingQuote;
  quoteError?: string;
  currency: string;
  pending: boolean;
}): PriceView {
  if (isCustomPlan(input.plan)) return { kind: "custom" };
  if (input.quote) {
    return {
      kind: "priced",
      discountBps: input.quote.discount_bps > 0 ? input.quote.discount_bps : null,
      lines: quotePriceLines(input.quote),
    };
  }
  if (isFreePlan(input.plan)) {
    return {
      kind: "priced",
      discountBps: null,
      lines: [{ fils: input.plan.monthly_fils, currency: input.currency, cadence: "amount" }],
    };
  }
  if (input.quoteError) return { kind: "error", message: input.quoteError };
  if (input.pending) return { kind: "loading" };
  return { kind: "loading" };
}

/** Quote lines, with the recurring charge and any one-time fee kept apart. An empty line list uses the quote totals. */
function quotePriceLines(quote: BillingQuote): PriceLine[] {
  if (quote.lines.length > 0) {
    return quote.lines.map((line) => ({
      fils: line.amount_fils,
      currency: quote.currency,
      cadence: line.recurring ? "cycle" : line.refundable ? "deposit" : "once",
      periodName: line.recurring ? quote.cycle_name : undefined,
    }));
  }
  const lines: PriceLine[] = [
    { fils: quote.recurring_fils, currency: quote.currency, cadence: "cycle", periodName: quote.cycle_name },
  ];
  if (quote.one_time_fils > 0) {
    lines.push({ fils: quote.one_time_fils, currency: quote.currency, cadence: "once" });
  }
  return lines;
}

/** A zero catalog price on an available add-on means Console has not set a price. It is not a free purchase. */
export function addonPriceView(item: MarketplaceItem, currency: string): PriceView {
  if (item.state === "custom") return { kind: "custom" };
  if (item.state === "unpriced") return { kind: "unpriced" };
  const lines: PriceLine[] = [];
  if (item.addon.monthly_fils > 0) lines.push({ fils: item.addon.monthly_fils, currency, cadence: "month" });
  if (item.addon.one_time_fils > 0) {
    lines.push({
      fils: item.addon.one_time_fils,
      currency,
      cadence: item.addon.refundable ? "deposit" : "once",
    });
  }
  if (lines.length === 0) {
    if (item.state === "available") return { kind: "unpriced" };
    return { kind: "none" };
  }
  return { kind: "priced", discountBps: null, lines };
}

export function addonPurchasable(item: MarketplaceItem): boolean {
  return item.state === "available" && (item.addon.monthly_fils > 0 || item.addon.one_time_fils > 0);
}

const MARKET_STATUS: Record<MarketplaceItem["state"], string> = {
  included: "Included",
  available: "Available",
  activated: "Activated",
  pending_payment: "Awaiting payment",
  pending_activation: "Pending activation",
  expired: "Expired",
  unavailable: "Unavailable",
  unpriced: "Price not configured",
  custom: "Contact sales",
};

export function marketplaceStatusLabel(state: MarketplaceItem["state"]): string {
  return MARKET_STATUS[state];
}

const SUBSCRIPTION_STATUS: Record<string, string> = {
  active: "Active",
  trialing: "Trial",
  past_due: "Past due",
  canceled: "Canceled",
};

export function subscriptionStatusLabel(status: string): string {
  return SUBSCRIPTION_STATUS[status] ?? status;
}

export function addonNextStep(item: MarketplaceItem, destination: string | null): AddonNextStep {
  if (item.state === "included") return { type: "text", label: "Included in your plan", translate: true };
  if (item.state === "activated") {
    return destination
      ? { type: "link", href: destination, label: "Open" }
      : { type: "text", label: "Activated", translate: true };
  }
  if (item.state === "pending_payment") return { type: "link", href: "/subscription", label: "View invoice" };
  if (item.state === "pending_activation") return { type: "text", label: "Payment verification in progress", translate: true };
  if (item.state === "expired") return { type: "link", href: "/subscription", label: "Review subscription" };
  if (addonPurchasable(item)) return { type: "purchase" };
  if (item.state === "custom") return { type: "text", label: "Contact sales", translate: true };
  if (item.state === "unpriced") return { type: "text", label: "Contact administrator", translate: true };
  if (item.state === "unavailable") {
    return item.reason
      ? { type: "text", label: item.reason, translate: false }
      : { type: "text", label: "Unavailable", translate: true };
  }
  return { type: "text", label: "Added on the package invoice", translate: true };
}

/**
 * Caps from the plan row. Usage counts are optional because the billing APIs do not return them.
 * A missing count stays unavailable. It is never rendered as zero usage.
 */
export function usageMetricViews(
  plan: BillingPlan | undefined,
  usage: Partial<Record<string, number | null | undefined>> = {},
): UsageMetricView[] {
  const limits = plan?.resource_limits ?? {};
  return USAGE_ORDER.map(([key, label]) => {
    if (!plan) return { key, label, state: "unavailable", used: null, limit: null };
    const raw = limits[key];
    if (raw === null) return { key, label, state: "unlimited", used: null, limit: null };
    const limit = typeof raw === "number" ? raw : key === "registers" && plan.included_registers > 0 ? plan.included_registers : null;
    if (limit === null) return { key, label, state: "unconfigured", used: null, limit: null };
    if (limit === 0) return { key, label, state: "zero", used: null, limit: 0 };
    const used = usage[key];
    if (typeof used !== "number") return { key, label, state: "unavailable", used: null, limit };
    return { key, label, state: "known", used, limit, tone: "neutral" };
  });
}

/** Backend usage payload. A missing count stays unavailable and is never shown as zero. */
export function presentUsage(payload: UsagePayload): UsageMetricView[] {
  return USAGE_ORDER.map(([key, fallback]) => {
    const row = payload.metrics[key];
    const label = row?.label || fallback;
    if (!row || !row.usage_available || row.status === "unavailable" || typeof row.used !== "number") {
      return { key, label, state: "unavailable" as const, used: null, limit: typeof row?.limit === "number" ? row.limit : null };
    }
    if (row.status === "unlimited") return { key, label, state: "unlimited", used: row.used, limit: null };
    if (row.status === "unconfigured") return { key, label, state: "unconfigured", used: row.used, limit: null };
    const tone: UsageTone = row.status === "limit_reached" ? "limit" : row.status === "near_limit" ? "warning" : "neutral";
    return {
      key,
      label,
      state: "known",
      used: row.used,
      limit: row.limit,
      tone,
      exceeded: row.exceeded,
    };
  });
}

/**
 * Suggests one published plan that raises the tightest finite cap.
 * Prices stay on the quote. A custom plan is contact-only.
 */
export function upgradeRecommendation(
  metrics: UsageMetricView[],
  plans: BillingPlan[],
  currentCode: string | null,
): { plan: BillingPlan; metric: string; contact: boolean } | null {
  const pressure = metrics.filter(
    (metric) => metric.state === "known" && (metric.tone === "warning" || metric.tone === "limit") && metric.limit !== null && metric.used !== null,
  );
  const worst = [...pressure].sort((left, right) => (right.used ?? 0) / (right.limit ?? 1) - (left.used ?? 0) / (left.limit ?? 1))[0];
  if (!worst || worst.limit === null || worst.used === null) return null;
  const fits = (plan: BillingPlan) => {
    const cap = plan.resource_limits?.[worst.key];
    if (cap === undefined) return false;
    if (cap === null) return true;
    return cap > (worst.limit ?? 0);
  };
  const candidates = plans.filter((plan) => plan.active && plan.code !== currentCode);
  const numeric = candidates.filter((plan) => !isCustomPlan(plan) && fits(plan)).sort((left, right) => left.sort_order - right.sort_order);
  if (numeric[0]) return { plan: numeric[0], metric: worst.label, contact: false };
  const custom = candidates.find((plan) => isCustomPlan(plan) && fits(plan));
  if (custom) return { plan: custom, metric: worst.label, contact: true };
  return null;
}

export interface CapabilityGroups {
  included: string[];
  purchased: string[];
  trial: string[];
  unavailable: string[];
}

/** Groups the feature-access payload. A feature is not shown as enabled only because it can be bought. */
export function capabilityGroups(
  features: Array<{ feature_key: string; label: string; state: string }>,
  purchasedKeys: ReadonlySet<string>,
  purchased: string[],
): CapabilityGroups {
  const included: string[] = [];
  const trial: string[] = [];
  const unavailable: string[] = [];
  for (const feature of features) {
    if (feature.state === "TRIAL_INCLUDED") trial.push(feature.label);
    else if (feature.state === "FEATURE_DISABLED") unavailable.push(feature.label);
    else if (feature.state === "INCLUDED" && !purchasedKeys.has(feature.feature_key)) included.push(feature.label);
  }
  return { included, purchased, trial, unavailable };
}

export function remainingCapacity(metric: UsageMetricView): number | null {
  if (metric.state !== "known" || metric.used === null || metric.limit === null) return null;
  return Math.max(0, metric.limit - metric.used);
}

export type AllowanceView = { state: "configured"; value: number } | { state: "unlimited" } | { state: "absent" };

/** Configured AI question allowance. There is no consumption counter, so this is not a usage bar. */
export function aiAllowanceView(plan: BillingPlan | undefined): AllowanceView {
  const raw = plan?.resource_limits?.ai_questions_per_month;
  if (raw === null) return { state: "unlimited" };
  if (typeof raw === "number") return { state: "configured", value: raw };
  return { state: "absent" };
}

const GROUP_LABEL: Record<string, string> = {
  selling: "POS & Checkout",
  inventory: "Inventory & Products",
  customers: "Customers & CRM",
  service: "Service",
  food_beverage: "Restaurant & Kitchen",
};

const FEATURE_GROUP: Record<string, string> = {
  ai_insights: "AI & Automation",
  deep_analytics: "Reports & Analytics",
  sales_insights: "Reports & Analytics",
  quotes_layaway: "Sales & Orders",
  sales_orders: "Sales & Orders",
  online_store: "Sales & Orders",
  promotions: "Sales & Orders",
  customer_reorders: "Sales & Orders",
  uae_einvoicing: "Finance & Accounting",
};

const GROUP_ORDER = [
  "POS & Checkout",
  "Sales & Orders",
  "Inventory & Products",
  "Customers & CRM",
  "Finance & Accounting",
  "Reports & Analytics",
  "AI & Automation",
  "Restaurant & Kitchen",
  "Service",
  "Other",
];

export function groupFeatures(features: ComparableFeature[]): { label: string; rows: ComparableFeature[] }[] {
  const visible = features.filter((feature) => comparableFeature(feature.state));
  const byGroup = new Map<string, ComparableFeature[]>();
  for (const feature of visible) {
    const spec = CAPABILITIES.find((row) => row.id === feature.feature_key);
    const label = FEATURE_GROUP[feature.feature_key] ?? GROUP_LABEL[spec?.group ?? ""] ?? "Other";
    const list = byGroup.get(label) ?? [];
    list.push(feature);
    byGroup.set(label, list);
  }
  return [...byGroup.entries()]
    .sort((left, right) => GROUP_ORDER.indexOf(left[0]) - GROUP_ORDER.indexOf(right[0]))
    .map(([label, rows]) => ({ label, rows }));
}

export type ComparisonCell = "included" | "addon" | "purchased" | "trial" | "absent" | "unconfigured" | "custom";

export interface ComparisonContext {
  currentCode: string | null;
  /** Activated add-on module keys. A pending invoice is not included. */
  purchasedKeys: ReadonlySet<string>;
  /** Catalog add-ons keyed by the capability they unlock. `priced` is false when Console has not set a price. */
  addons: ReadonlyMap<string, { priced: boolean; custom?: boolean }>;
  /** Capabilities named on at least one visible plan. Those stay plan features, not unpriced add-ons. */
  claimedKeys?: ReadonlySet<string>;
}

const EMPTY_COMPARISON: ComparisonContext = { currentCode: null, purchasedKeys: new Set(), addons: new Map() };

/** One comparison cell. Plan modules, the business preset, and published add-ons decide it. A pending payment is not an entitlement. */
export function comparisonCell(
  plan: BillingPlan,
  feature: { feature_key: string; state: string; baseline?: boolean; grandfathered?: boolean },
  context: ComparisonContext = EMPTY_COMPARISON,
): ComparisonCell {
  const key = feature.feature_key;
  if (plan.included_modules.includes(key)) return "included";
  const onCurrent = plan.code === context.currentCode;
  if (onCurrent && feature.state === "TRIAL_INCLUDED") return "trial";
  if (!isCustomPlan(plan) && feature.baseline) return "included";
  const addon = context.addons.get(key);
  const claimed = context.claimedKeys?.has(key) === true;
  if (addon && !claimed) {
    if (onCurrent && context.purchasedKeys.has(key)) return "purchased";
    if (addon.custom && !addon.priced) return "custom";
    return addon.priced ? "addon" : "unconfigured";
  }
  if (onCurrent && addon && context.purchasedKeys.has(key)) return "purchased";
  if (isCustomPlan(plan)) return "custom";
  if (onCurrent && feature.grandfathered) return "included";
  return "absent";
}

export function addonIndex(items: readonly MarketplaceItem[]): { purchasedKeys: Set<string>; addons: Map<string, { priced: boolean; custom?: boolean }> } {
  const purchasedKeys = new Set<string>();
  const addons = new Map<string, { priced: boolean; custom?: boolean }>();
  for (const item of items) {
    const priced = item.addon.monthly_fils > 0 || item.addon.one_time_fils > 0;
    for (const key of item.addon.module_keys) {
      const previous = addons.get(key);
      addons.set(key, {
        priced: previous?.priced === true || priced,
        custom: previous?.custom === true || item.state === "custom",
      });
      if (item.state === "activated") purchasedKeys.add(key);
    }
  }
  return { purchasedKeys, addons };
}

export type LimitCell = { state: "configured"; value: number } | { state: "unlimited" } | { state: "unconfigured" };

/** A missing cap stays unconfigured. Null is the catalog's explicit unlimited value. */
export function planLimitCell(plan: BillingPlan, key: string): LimitCell {
  const limits = plan.resource_limits ?? {};
  if (Object.prototype.hasOwnProperty.call(limits, key)) {
    const raw = limits[key];
    if (raw === null) return { state: "unlimited" };
    if (typeof raw === "number") return { state: "configured", value: raw };
  }
  if (key === "registers" && !(key in limits) && plan.included_registers > 0) {
    return { state: "configured", value: plan.included_registers };
  }
  return { state: "unconfigured" };
}

export type FeatureSuggestion =
  | { kind: "plan"; plan: BillingPlan; feature: string; contact: boolean }
  | { kind: "addon"; name: string; feature: string };

/** One catalog-backed next step. The plan must actually include the feature, or the add-on must have a price. */
export function featureRecommendation(
  features: readonly ComparableFeature[],
  plans: readonly BillingPlan[],
  context: ComparisonContext,
): FeatureSuggestion | null {
  for (const feature of features) {
    if (feature.state === "PLUGIN_REQUIRED") {
      const addon = context.addons.get(feature.feature_key);
      if (addon?.priced && feature.plugin_name) return { kind: "addon", name: feature.plugin_name, feature: feature.label };
      continue;
    }
    if (feature.state !== "UPGRADE_REQUIRED") continue;
    const match = plans.find(
      (plan) => plan.code !== context.currentCode && plan.included_modules.includes(feature.feature_key),
    );
    if (!match) continue;
    return { kind: "plan", plan: match, feature: feature.label, contact: isCustomPlan(match) };
  }
  return null;
}

export function differingFeatures<T extends ComparableFeature>(
  features: readonly T[],
  plans: readonly BillingPlan[],
  context: ComparisonContext = EMPTY_COMPARISON,
): T[] {
  return features.filter((feature) => {
    const marks = new Set(plans.map((plan) => comparisonCell(plan, feature, context)));
    return marks.size > 1;
  });
}

export function categorySlug(label: string): string {
  return label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "group";
}

const CHANGE_STATUS: Record<string, string> = {
  quoted: "Quoted",
  pending_payment: "Awaiting payment",
  payment_submitted: "Payment proof submitted",
  completed: "Completed",
  cancelled: "Cancelled",
  rejected: "Rejected",
  expired: "Expired",
  failed: "Failed",
};

export function changeStatusLabel(status: string): string {
  return CHANGE_STATUS[status] ?? status;
}

export function changeNextAction(status: string, rejection: string | null): string {
  if (status === "pending_payment" && rejection) return "Submit a corrected payment proof.";
  if (status === "quoted") return "Generate the invoice to continue.";
  if (status === "pending_payment") return "Submit the transfer proof.";
  if (status === "payment_submitted") return "Wait for payment verification.";
  if (status === "completed") return "This plan change is complete.";
  if (status === "cancelled") return "This request was cancelled.";
  if (status === "rejected") return "This request was rejected.";
  if (status === "expired") return "This quote expired.";
  if (status === "failed") return "This request failed.";
  return "";
}

export function planChangeIsOpen(status: string): boolean {
  return status === "quoted" || status === "pending_payment" || status === "payment_submitted";
}
