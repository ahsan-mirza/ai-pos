import { cycleAmountFils } from "@ai-pos/shared-types";

/** Starting catalog from `ensure_catalog` in the API. Used when the public catalog cannot be loaded. */

export interface Plan {
  code: string;
  name: string;
  included_registers: number;
  included_modules: string[];
  monthly_fils: number;
  trial_days: number;
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

export interface PublicCatalog {
  plans: Plan[];
  cycles: Cycle[];
  addons: Addon[];
  fees: Fee[];
  hardware: PublicHardware[];
}

export const SEED: PublicCatalog = {
  plans: [
    {
      code: "LITE",
      name: "Lite",
      included_registers: 1,
      included_modules: ["promotions", "loyalty"],
      monthly_fils: 14_900,
      trial_days: 14,
    },
    {
      code: "STANDARD",
      name: "Standard",
      included_registers: 3,
      included_modules: ["promotions", "loyalty", "card_terminals", "quotes_layaway"],
      monthly_fils: 29_900,
      trial_days: 14,
    },
    {
      code: "PRO",
      name: "Pro",
      included_registers: 8,
      included_modules: ["promotions", "loyalty", "card_terminals", "bnpl", "gift_cards", "kds", "tables"],
      monthly_fils: 49_900,
      trial_days: 30,
    },
  ],
  cycles: [
    { code: "MONTHLY", name: "Monthly", months: 1, discount_bps: 0 },
    { code: "QUARTERLY", name: "Quarterly", months: 3, discount_bps: 500 },
    { code: "HALF_YEARLY", name: "Half-Yearly", months: 6, discount_bps: 1_200 },
    { code: "ANNUAL", name: "Annual", months: 12, discount_bps: 2_500 },
  ],
  addons: [
    {
      code: "hardware_lease",
      name: "Hardware lease",
      description: "Register hardware, rented. The one-time amount is a refundable deposit.",
      monthly_fils: 15_000,
      one_time_fils: 50_000,
      refundable: true,
      module_keys: [],
      active: true,
    },
    {
      code: "equipment_protection",
      name: "Equipment protection",
      description: "Covers leased hardware.",
      monthly_fils: 3_900,
      one_time_fils: 0,
      refundable: false,
      module_keys: [],
      active: true,
    },
    {
      code: "extra_register",
      name: "Extra register",
      description: "A register beyond the ones included in the package.",
      monthly_fils: 4_900,
      one_time_fils: 0,
      refundable: false,
      module_keys: [],
      active: true,
    },
  ],
  fees: [{ code: "onboarding", name: "Onboarding", amount_fils: 25_000 }],
  hardware: [],
};

/** Same integer fils rounding as `cycle_amount` in the API. */
export function cycleAmount(monthlyFils: number, months: number, discountBps: number): number {
  return cycleAmountFils(monthlyFils, months, discountBps);
}

export function aed(fils: number): string {
  return new Intl.NumberFormat("en-AE", {
    style: "currency",
    currency: "AED",
    minimumFractionDigits: fils % 100 === 0 ? 0 : 2,
  }).format(fils / 100);
}

export const STORE_MIN = 1;
export const STORE_MAX = 24;

export interface Estimate {
  stores: number;
  registers: number;
  cycle: Cycle;
  /** Discounted package for every store over this cycle. */
  packageFils: number;
  /** Same package with the cycle discount removed. */
  packageListFils: number;
  /** Package list minus the discounted package. Hardware, fees, and deposits are excluded. */
  savingFils: number;
  /** Face-value hardware rent for one month, one lease per included register. */
  leaseMonthlyFils: number | null;
  /** Face-value hardware rent for the whole cycle. The cycle discount does not apply. */
  leaseCycleFils: number | null;
  depositFils: number | null;
  protectionMonthlyFils: number | null;
  protectionCycleFils: number | null;
  /** Onboarding once per store, the same count the payback figure already used. */
  onboardingFils: number | null;
  onboardingUnitFils: number | null;
  recurringCycleFils: number;
  dueNowFils: number;
  nextCycleFils: number;
  /** Discounted package for one store for the whole cycle. */
  perStoreFils: number;
  discountPercent: number;
  paybackMonths: number | null;
  /** Cycle with the lowest effective monthly package price, when it beats paying monthly. */
  bestValueCode: string | null;
}

function clampStores(stores: number): number {
  if (!Number.isFinite(stores)) return STORE_MIN;
  return Math.min(STORE_MAX, Math.max(STORE_MIN, Math.trunc(stores)));
}

/** Lowest effective monthly package price. A tie prefers the longer cycle. */
export function bestValueCycle(plan: Plan, cycles: Cycle[]): string | null {
  let best: { code: string; monthly: number; months: number } | null = null;
  for (const cycle of cycles) {
    if (cycle.months < 1) continue;
    const monthly = cycleAmount(plan.monthly_fils, cycle.months, cycle.discount_bps) / cycle.months;
    const cheaper = best === null || monthly < best.monthly - 1e-6;
    const tie = best !== null && Math.abs(monthly - best.monthly) <= 1e-6 && cycle.months > best.months;
    if (cheaper || tie) best = { code: cycle.code, monthly, months: cycle.months };
  }
  if (best === null) return null;
  const undiscounted = cycles.find((cycle) => cycle.months === 1 && cycle.discount_bps === 0);
  if (undiscounted && best.code === undiscounted.code) return null;
  return best.code;
}

export function estimate(
  plan: Plan,
  stores: number,
  catalog: PublicCatalog,
  cycleCode: string,
  options?: { protection?: boolean },
): Estimate {
  const count = clampStores(stores);
  const cycle =
    catalog.cycles.find((item) => item.code === cycleCode) ??
    catalog.cycles.find((item) => item.code === "ANNUAL") ??
    catalog.cycles[0] ??
    { code: "MONTHLY", name: "Monthly", months: 1, discount_bps: 0 };
  const hardware = catalog.addons.find((addon) => addon.code === "hardware_lease");
  const protection = catalog.addons.find((addon) => addon.code === "equipment_protection");
  const onboarding = catalog.fees.find((fee) => fee.code === "onboarding");
  const registers = plan.included_registers * count;
  const perStoreFils = cycleAmount(plan.monthly_fils, cycle.months, cycle.discount_bps);
  const packageFils = perStoreFils * count;
  const packageListFils = plan.monthly_fils * cycle.months * count;
  const savingFils = packageListFils - packageFils;
  const leaseMonthlyFils = hardware ? hardware.monthly_fils * registers : null;
  const leaseCycleFils = leaseMonthlyFils === null ? null : leaseMonthlyFils * cycle.months;
  const depositFils = hardware && hardware.one_time_fils > 0 ? hardware.one_time_fils * registers : null;
  const protectionOn = options?.protection === true && protection !== undefined;
  const protectionMonthlyFils = protectionOn ? protection.monthly_fils * registers : null;
  const protectionCycleFils = protectionMonthlyFils === null ? null : protectionMonthlyFils * cycle.months;
  const onboardingUnitFils = onboarding?.amount_fils ?? null;
  const onboardingFils = onboardingUnitFils === null ? null : onboardingUnitFils * count;
  const recurringCycleFils = packageFils + (leaseCycleFils ?? 0) + (protectionCycleFils ?? 0);
  const dueNowFils = recurringCycleFils + (onboardingFils ?? 0) + (depositFils ?? 0);
  const perMonth = cycle.months > 0 ? savingFils / cycle.months : 0;
  const paybackMonths =
    onboardingUnitFils !== null && perMonth > 0 ? (onboardingUnitFils * count) / perMonth : null;
  return {
    stores: count,
    registers,
    cycle,
    packageFils,
    packageListFils,
    savingFils,
    leaseMonthlyFils,
    leaseCycleFils,
    depositFils,
    protectionMonthlyFils,
    protectionCycleFils,
    onboardingFils,
    onboardingUnitFils,
    recurringCycleFils,
    dueNowFils,
    nextCycleFils: recurringCycleFils,
    perStoreFils,
    discountPercent: cycle.discount_bps / 100,
    paybackMonths,
    bestValueCode: bestValueCycle(plan, catalog.cycles),
  };
}

/** Short note for the existing demo form. Not a binding quote. */
export function estimateNote(plan: Plan, quote: Estimate): string {
  const storeWord = quote.stores === 1 ? "store" : "stores";
  const registerWord = quote.registers === 1 ? "register" : "registers";
  const lines = [
    "AxizPOS estimate, not a final quote.",
    `${plan.name}, ${quote.stores} ${storeWord}, ${quote.registers} included ${registerWord}, ${quote.cycle.name} (${quote.discountPercent}% off the package).`,
    `Package this cycle: ${aed(quote.packageFils)}.`,
    quote.leaseCycleFils !== null ? `Hardware lease this cycle: ${aed(quote.leaseCycleFils)}.` : "",
    quote.protectionCycleFils !== null ? `Equipment protection this cycle: ${aed(quote.protectionCycleFils)}.` : "",
    quote.onboardingFils !== null ? `Onboarding: ${aed(quote.onboardingFils)} once.` : "",
    quote.depositFils !== null ? `Refundable deposit: ${aed(quote.depositFils)}.` : "",
    `Due at the start: ${aed(quote.dueNowFils)}.`,
    quote.savingFils > 0
      ? `Package saving vs monthly over ${quote.cycle.months} ${quote.cycle.months === 1 ? "month" : "months"}: ${aed(quote.savingFils)}.`
      : "",
  ];
  return lines.filter((line) => line.length > 0).join(" ").slice(0, 500);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
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
  return {
    code: value.code,
    name: value.name,
    included_registers: value.included_registers,
    included_modules: modules as string[],
    monthly_fils: value.monthly_fils,
    trial_days: value.trial_days,
  };
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
  return {
    code: value.code,
    name: value.name,
    description: typeof value.description === "string" ? value.description : "",
    monthly_fils: value.monthly_fils,
    one_time_fils: value.one_time_fils,
    refundable: value.refundable === true,
    module_keys: keys,
    active: value.active !== false,
  };
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
  return { plans, cycles, addons, fees, hardware };
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
    const response = await fetch(url);
    if (!response.ok) return { catalog: SEED, live: false };
    const parsed = parseCatalog(await response.json());
    return parsed ? { catalog: parsed, live: true } : { catalog: SEED, live: false };
  } catch {
    return { catalog: SEED, live: false };
  }
}
