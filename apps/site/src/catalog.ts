import {
  CAPABILITIES,
  PROFILE_ELIGIBLE,
  cycleAmountFils,
  formatMoney,
  isCapability,
  type BusinessProfile,
} from "@ai-pos/shared-types";

export interface Plan {
  code: string;
  name: string;
  included_registers: number;
  included_modules: string[];
  monthly_fils: number;
  trial_days: number;
  active: boolean;
  sort_order: number;
  catalog_family: "current" | "legacy";
  custom_pricing: boolean;
  /** Configured caps. A null value means that cap is not enforced. */
  resource_limits: Record<string, number | null>;
  /** Published country list prices. Empty when this plan has no regional price. */
  prices: CountryPrice[];
}

export interface CountryPrice {
  country: string;
  currency: string;
  monthly_fils: number;
}

export interface Cycle {
  code: string;
  name: string;
  months: number;
  discount_bps: number;
}

export interface Addon {
  code: string;
  name: string;
  description: string;
  monthly_fils: number;
  one_time_fils: number;
  refundable: boolean;
  /** Capability ids this priced add-on is allowed to sell. Empty when it does not unlock a product module. */
  module_keys: string[];
  active: boolean;
  sort_order: number;
  short_description: string;
  category: string;
  featured: boolean;
  benefits: AddonBenefit[];
  documentation_url: string;
}

export interface AddonBenefit {
  title: string;
  description: string;
}

export interface Fee {
  code: string;
  name: string;
  amount_fils: number;
}

export interface PublicHardware {
  id: string;
  sku: string;
  name: string;
  category_name: string;
  description: string;
  image_url: string | null;
  lease_available: boolean;
  purchase_available: boolean;
  monthly_fils: number;
  deposit_fils: number;
  fee_fils: number;
  purchase_fils: number | null;
  delivery_fils: number;
  currency: string;
}

export interface PublicTrial {
  enabled: boolean;
  days: number;
  plan_code: string;
  eligible_plans: string[];
}

export interface PublicCatalog {
  plans: Plan[];
  cycles: Cycle[];
  addons: Addon[];
  fees: Fee[];
  hardware: PublicHardware[];
  /** Null when the payload did not publish a new-plan annual rate. */
  current_annual_discount_bps: number | null;
  promotional_trial: PublicTrial;
}

export const EMPTY_CATALOG: PublicCatalog = {
  plans: [],
  cycles: [],
  addons: [],
  fees: [],
  hardware: [],
  current_annual_discount_bps: null,
  promotional_trial: { enabled: false, days: 0, plan_code: "", eligible_plans: [] },
};

const CURRENT_CODES = new Set(["FREE", "GROWTH", "PRO_AI", "ENTERPRISE"]);

/** Same integer fils rounding as `cycle_amount` in the API. */
export function cycleAmount(monthlyFils: number, months: number, discountBps: number): number {
  return cycleAmountFils(monthlyFils, months, discountBps);
}

export function aed(fils: number): string {
  return money(fils, "AED");
}

/** Formats fils in the currency the catalog published. Digits stay Western. */
export function money(fils: number, currency: string): string {
  const code = /^[A-Z]{3}$/.test(currency) ? currency : "AED";
  return formatMoney(fils, code, "en");
}

const LIMIT_LABELS: Record<string, string> = {
  branches: "Branches",
  registers: "Registers",
  staff: "Staff",
  products: "Products",
  customers: "Customers",
  sales_history_days: "Sales history",
  ai_questions_per_month: "AI questions",
};

export function isCustomPlan(plan: Plan): boolean {
  return plan.custom_pricing || plan.code === "ENTERPRISE";
}

export function isFreePlan(plan: Plan): boolean {
  return plan.code === "FREE";
}

/** Current catalog. Legacy plans stay out of the public grid. */
export function showcasePlans(catalog: PublicCatalog): Plan[] {
  return catalog.plans
    .filter((plan) => plan.active && plan.catalog_family === "current")
    .sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name));
}

export function legacyPlanNames(catalog: PublicCatalog): string[] {
  return catalog.plans.filter((plan) => plan.active && plan.catalog_family === "legacy").map((plan) => plan.name);
}

/** New plans use the published annual rate. Other cycles, and legacy plans, use the cycle row. */
export function cycleDiscountBps(plan: Plan, cycle: Cycle, catalog: PublicCatalog): number {
  if (plan.catalog_family === "current" && cycle.code === "ANNUAL" && catalog.current_annual_discount_bps !== null) {
    return catalog.current_annual_discount_bps;
  }
  return cycle.discount_bps;
}

export interface PublishedPrice {
  kind: "free" | "custom" | "priced" | "unavailable";
  amountFils: number | null;
  discountBps: number;
  currency: string;
}

/** Countries that have at least one published price on a current plan. */
export function publishedCountries(catalog: PublicCatalog): string[] {
  const seen: string[] = [];
  for (const plan of showcasePlans(catalog)) {
    for (const price of plan.prices) {
      if (!seen.includes(price.country)) seen.push(price.country);
    }
  }
  return seen;
}

/** AE when that row exists, otherwise the first published country. */
export function defaultCountry(catalog: PublicCatalog): string | null {
  const countries = publishedCountries(catalog);
  if (countries.includes("AE")) return "AE";
  return countries[0] ?? null;
}

/**
 * One subscription for the selected cycle and country.
 * A current paid plan uses its published country row. A zero amount is a price only for Free.
 */
export function publishedPrice(plan: Plan, cycle: Cycle, catalog: PublicCatalog, country: string | null): PublishedPrice {
  const discountBps = cycleDiscountBps(plan, cycle, catalog);
  if (isCustomPlan(plan)) return { kind: "custom", amountFils: null, discountBps, currency: "" };
  if (isFreePlan(plan)) return { kind: "free", amountFils: 0, discountBps: 0, currency: "" };
  const regional = country ? plan.prices.find((row) => row.country === country) : undefined;
  if (regional) {
    if (regional.monthly_fils <= 0) return { kind: "unavailable", amountFils: null, discountBps, currency: regional.currency };
    return {
      kind: "priced",
      amountFils: cycleAmount(regional.monthly_fils, cycle.months, discountBps),
      discountBps,
      currency: regional.currency,
    };
  }
  if (country && plan.catalog_family === "current") {
    return { kind: "unavailable", amountFils: null, discountBps, currency: "" };
  }
  if (plan.monthly_fils <= 0) return { kind: "unavailable", amountFils: null, discountBps, currency: "AED" };
  return {
    kind: "priced",
    amountFils: cycleAmount(plan.monthly_fils, cycle.months, discountBps),
    discountBps,
    currency: "AED",
  };
}

export interface PlanLimitLine {
  key: string;
  label: string;
  text: string;
}

/** Configured caps only. Missing usage is not shown as zero. */
export function planLimitLines(plan: Plan): PlanLimitLine[] {
  const rows: PlanLimitLine[] = [];
  if (plan.included_registers > 0) {
    rows.push({ key: "included_registers", label: "Registers", text: String(plan.included_registers) });
  }
  for (const [key, value] of Object.entries(plan.resource_limits)) {
    if (typeof value !== "number" || key === "registers") continue;
    const suffix = key === "sales_history_days" ? " days" : "";
    rows.push({ key, label: LIMIT_LABELS[key] ?? key.replaceAll("_", " "), text: `${value}${suffix}` });
  }
  return rows;
}

export interface ComparisonRow {
  key: string;
  pluginCodes: string[];
}

function fitsProfile(key: string, profile: BusinessProfile | null): boolean {
  if (profile === null || !isCapability(key)) return true;
  return PROFILE_ELIGIBLE[profile].includes(key);
}

/**
 * Every published capability that a current plan includes or a published add-on sells.
 * The cell mark, not the row, says whether that plan includes it.
 */
export function comparisonRows(plans: readonly Plan[], addons: readonly Addon[], profile: BusinessProfile | null = null): ComparisonRow[] {
  const plugins = new Map<string, string[]>();
  for (const addon of addons) {
    if (!addon.active || addon.module_keys.length === 0) continue;
    for (const key of addon.module_keys) {
      if (!fitsProfile(key, profile)) continue;
      const codes = plugins.get(key) ?? [];
      if (!codes.includes(addon.code)) codes.push(addon.code);
      plugins.set(key, codes);
    }
  }
  const keys: string[] = [];
  for (const plan of plans) {
    for (const key of plan.included_modules) {
      if (!fitsProfile(key, profile) || keys.includes(key)) continue;
      keys.push(key);
    }
  }
  for (const key of plugins.keys()) {
    if (!keys.includes(key)) keys.push(key);
  }
  return keys.map((key) => ({ key, pluginCodes: plugins.get(key) ?? [] }));
}

/** Published add-ons a visitor can buy. Draft and archived rows never reach this list. */
export function publicPlugins(addons: readonly Addon[], profile: BusinessProfile | null = null): Addon[] {
  return addons
    .filter((addon) => addon.active)
    .filter((addon) => {
      if (profile === null) return true;
      const keys = addon.module_keys.filter((key) => isCapability(key));
      if (keys.length === 0) return true;
      return keys.some((key) => PROFILE_ELIGIBLE[profile].includes(key));
    })
    .sort((left, right) => Number(right.featured) - Number(left.featured) || left.sort_order - right.sort_order || left.name.localeCompare(right.name));
}

/**
 * Add-on amounts on the public catalog are AED fils. Another country's currency is not invented from that figure.
 */
export function addonPriceText(addon: Addon, currency: string | null): string | null {
  if (currency !== null && currency !== "AED") return null;
  const parts: string[] = [];
  if (addon.monthly_fils > 0) parts.push(`${money(addon.monthly_fils, "AED")} / month`);
  if (addon.one_time_fils > 0) {
    parts.push(addon.refundable ? `${money(addon.one_time_fils, "AED")} refundable deposit` : `${money(addon.one_time_fils, "AED")} once`);
  }
  return parts.length > 0 ? parts.join(" · ") : null;
}

export type ComparisonMark = "included" | "addon" | "custom" | "absent";

/**
 * Included comes only from the plan's published module list.
 * A published add-on that sells the same module is optional, not part of the plan.
 * A custom-priced plan negotiates anything it does not already include and does not sell as an add-on.
 */
export function comparisonMark(plan: Plan, row: ComparisonRow): ComparisonMark {
  if (plan.included_modules.includes(row.key)) return "included";
  if (row.pluginCodes.length > 0) return "addon";
  if (isCustomPlan(plan)) return "custom";
  return "absent";
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
  deep_analytics: "AI & Automation",
  sales_insights: "Sales & Orders",
  quotes_layaway: "Sales & Orders",
  sales_orders: "Sales & Orders",
  promotions: "Sales & Orders",
  customer_reorders: "Sales & Orders",
  uae_einvoicing: "Integrations & Extensions",
  online_store: "Integrations & Extensions",
  card_terminals: "Integrations & Extensions",
  bnpl: "Integrations & Extensions",
  delivery_integrations: "Integrations & Extensions",
  axiz_reach: "Integrations & Extensions",
  multi_currency: "Integrations & Extensions",
};

const GROUP_ORDER = [
  "POS & Checkout",
  "Sales & Orders",
  "Inventory & Products",
  "Customers & CRM",
  "Finance & Accounting",
  "AI & Automation",
  "Restaurant & Kitchen",
  "Integrations & Extensions",
  "Administration & Security",
  "Service",
  "Other",
];

/** Display group for a catalog feature key. Empty groups are omitted by the caller. */
export function featureGroup(key: string): string {
  const override = FEATURE_GROUP[key];
  if (override) return override;
  const spec = CAPABILITIES.find((row) => row.id === key);
  return GROUP_LABEL[spec?.group ?? ""] ?? "Other";
}

export function groupedComparison(rows: readonly ComparisonRow[]): { label: string; rows: ComparisonRow[] }[] {
  const byGroup = new Map<string, ComparisonRow[]>();
  for (const row of rows) {
    const label = featureGroup(row.key);
    const list = byGroup.get(label) ?? [];
    list.push(row);
    byGroup.set(label, list);
  }
  return [...byGroup.entries()]
    .sort((left, right) => GROUP_ORDER.indexOf(left[0]) - GROUP_ORDER.indexOf(right[0]))
    .map(([label, groupRows]) => ({ label, rows: groupRows }));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function readLimits(value: unknown): Record<string, number | null> {
  if (!isRecord(value)) return {};
  const limits: Record<string, number | null> = {};
  for (const [key, raw] of Object.entries(value)) {
    if (typeof raw === "number") limits[key] = raw;
    else if (raw === null) limits[key] = null;
  }
  return limits;
}

function readPlan(value: unknown): Plan | null {
  if (!isRecord(value)) return null;
  const modules = value.included_modules;
  if (
    typeof value.code !== "string" ||
    typeof value.name !== "string" ||
    typeof value.included_registers !== "number" ||
    typeof value.monthly_fils !== "number" ||
    typeof value.trial_days !== "number" ||
    !Array.isArray(modules) ||
    modules.some((item) => typeof item !== "string")
  ) {
    return null;
  }
  const family =
    value.catalog_family === "current" || value.catalog_family === "legacy"
      ? value.catalog_family
      : CURRENT_CODES.has(value.code)
        ? "current"
        : "legacy";
  return {
    code: value.code,
    name: value.name,
    included_registers: value.included_registers,
    included_modules: modules as string[],
    monthly_fils: value.monthly_fils,
    trial_days: value.trial_days,
    active: value.active !== false,
    sort_order: typeof value.sort_order === "number" ? value.sort_order : 0,
    catalog_family: family,
    custom_pricing: value.custom_pricing === true || value.code === "ENTERPRISE",
    resource_limits: readLimits(value.resource_limits),
    prices: readPrices(value.prices),
  };
}

function readPrices(value: unknown): CountryPrice[] {
  if (!Array.isArray(value)) return [];
  const prices: CountryPrice[] = [];
  for (const row of value) {
    if (!isRecord(row)) continue;
    if (typeof row.country !== "string" || typeof row.currency !== "string" || typeof row.monthly_fils !== "number") continue;
    prices.push({ country: row.country, currency: row.currency, monthly_fils: row.monthly_fils });
  }
  return prices;
}

function readCycle(value: unknown): Cycle | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.code !== "string" ||
    typeof value.name !== "string" ||
    typeof value.months !== "number" ||
    typeof value.discount_bps !== "number"
  ) {
    return null;
  }
  return { code: value.code, name: value.name, months: value.months, discount_bps: value.discount_bps };
}

function readAddon(value: unknown): Addon | null {
  if (!isRecord(value)) return null;
  if (
    typeof value.code !== "string" ||
    typeof value.name !== "string" ||
    typeof value.monthly_fils !== "number" ||
    typeof value.one_time_fils !== "number"
  ) {
    return null;
  }
  const keys = Array.isArray(value.module_keys) ? value.module_keys.filter((item) => typeof item === "string") : [];
  const listing = isRecord(value.listing) ? value.listing : null;
  const publication = listing && typeof listing.publication === "string" ? listing.publication : "published";
  if (publication === "draft" || publication === "archived") return null;
  const short =
    listing && typeof listing.short_description === "string" ? listing.short_description : "";
  const category = listing && typeof listing.category === "string" ? listing.category : "";
  const documentation = listing && typeof listing.documentation_url === "string" ? listing.documentation_url : "";
  return {
    code: value.code,
    name: value.name,
    description: typeof value.description === "string" ? value.description : "",
    monthly_fils: value.monthly_fils,
    one_time_fils: value.one_time_fils,
    refundable: value.refundable === true,
    module_keys: keys,
    active: value.active !== false,
    sort_order: typeof value.sort_order === "number" ? value.sort_order : 0,
    short_description: short,
    category,
    featured: listing?.featured === true,
    benefits: readBenefits(listing?.benefits),
    documentation_url: documentation.startsWith("http://") || documentation.startsWith("https://") ? documentation : "",
  };
}

function readBenefits(value: unknown): AddonBenefit[] {
  if (!Array.isArray(value)) return [];
  const benefits: AddonBenefit[] = [];
  for (const row of value) {
    if (!isRecord(row)) continue;
    const title = typeof row.title === "string" ? row.title : "";
    const description = typeof row.description === "string" ? row.description : "";
    if (title === "" && description === "") continue;
    benefits.push({ title, description });
  }
  return benefits;
}

function readFee(value: unknown): Fee | null {
  if (!isRecord(value)) return null;
  if (typeof value.code !== "string" || typeof value.name !== "string" || typeof value.amount_fils !== "number") {
    return null;
  }
  return { code: value.code, name: value.name, amount_fils: value.amount_fils };
}

export function parseCatalog(value: unknown): PublicCatalog | null {
  if (!isRecord(value)) return null;
  const plans = Array.isArray(value.plans) ? value.plans.map(readPlan).filter((row) => row !== null) : [];
  const cycles = Array.isArray(value.cycles) ? value.cycles.map(readCycle).filter((row) => row !== null) : [];
  const addons = Array.isArray(value.addons) ? value.addons.map(readAddon).filter((row) => row !== null) : [];
  const fees = Array.isArray(value.fees) ? value.fees.map(readFee).filter((row) => row !== null) : [];
  const hardware = Array.isArray(value.hardware) ? value.hardware.map(readHardware).filter((row) => row !== null) : [];
  if (plans.length === 0) return null;
  const trial = isRecord(value.promotional_trial) ? value.promotional_trial : null;
  const eligible = trial && Array.isArray(trial.eligible_plans) ? trial.eligible_plans.filter((item) => typeof item === "string") : [];
  return {
    plans,
    cycles,
    addons,
    fees,
    hardware,
    current_annual_discount_bps: typeof value.current_annual_discount_bps === "number" ? value.current_annual_discount_bps : null,
    promotional_trial: {
      enabled: trial?.enabled === true,
      days: trial && typeof trial.days === "number" ? trial.days : 0,
      plan_code: trial && typeof trial.plan_code === "string" ? trial.plan_code : "",
      eligible_plans: eligible,
    },
  };
}

function readHardware(value: unknown): PublicHardware | null {
  if (!isRecord(value)) return null;
  const id = typeof value.id === "string" ? value.id : "";
  const name = typeof value.name === "string" ? value.name : "";
  if (id === "" || name === "") return null;
  if (value.available === false || value.active === false || value.archived === true) return null;
  const purchase = typeof value.purchase_fils === "number" ? value.purchase_fils : null;
  return {
    id,
    sku: typeof value.sku === "string" ? value.sku : "",
    name,
    category_name: typeof value.category_name === "string" ? value.category_name : "",
    description: typeof value.description === "string" ? value.description : "",
    image_url: typeof value.image_url === "string" && value.image_url !== "" ? value.image_url : null,
    lease_available: value.lease_available === true,
    purchase_available: value.purchase_available === true,
    monthly_fils: typeof value.monthly_fils === "number" ? value.monthly_fils : 0,
    deposit_fils: typeof value.deposit_fils === "number" ? value.deposit_fils : 0,
    fee_fils: typeof value.fee_fils === "number" ? value.fee_fils : 0,
    purchase_fils: purchase,
    delivery_fils: typeof value.delivery_fils === "number" ? value.delivery_fils : 0,
    currency: typeof value.currency === "string" ? value.currency : "AED",
  };
}

export async function loadCatalog(url: string): Promise<{ catalog: PublicCatalog; live: boolean }> {
  try {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) return { catalog: EMPTY_CATALOG, live: false };
    const parsed = parseCatalog(await response.json());
    return parsed ? { catalog: parsed, live: true } : { catalog: EMPTY_CATALOG, live: false };
  } catch {
    return { catalog: EMPTY_CATALOG, live: false };
  }
}
