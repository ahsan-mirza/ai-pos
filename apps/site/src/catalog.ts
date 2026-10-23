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
}

export interface Fee {
  code: string;
  name: string;
  amount_fils: number;
}

export interface PublicCatalog {
  plans: Plan[];
  cycles: Cycle[];
  addons: Addon[];
  fees: Fee[];
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
    { code: "HALF_YEARLY", name: "Half-yearly", months: 6, discount_bps: 1_200 },
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
    },
    {
      code: "equipment_protection",
      name: "Equipment protection",
      description: "Covers leased hardware.",
      monthly_fils: 3_900,
      one_time_fils: 0,
      refundable: false,
    },
    {
      code: "extra_register",
      name: "Extra register",
      description: "A register beyond the ones included in the package.",
      monthly_fils: 4_900,
      one_time_fils: 0,
      refundable: false,
    },
  ],
  fees: [{ code: "onboarding", name: "Onboarding", amount_fils: 25_000 }],
};

/** Same integer fils rounding as `cycle_amount` in the API. */
export function cycleAmount(monthlyFils: number, months: number, discountBps: number): number {
  return Math.floor((monthlyFils * months * (10_000 - discountBps)) / 10_000);
}

export function aed(fils: number): string {
  return new Intl.NumberFormat("en-AE", {
    style: "currency",
    currency: "AED",
    minimumFractionDigits: fils % 100 === 0 ? 0 : 2,
  }).format(fils / 100);
}

export interface Estimate {
  registers: number;
  software: number;
  lease: number | null;
  deposit: number | null;
  saving: number | null;
  paybackMonths: number | null;
  discountPercent: number | null;
  cycleName: string | null;
  onboarding: number | null;
}

export function estimate(plan: Plan, stores: number, catalog: PublicCatalog): Estimate {
  const hardware = catalog.addons.find((addon) => addon.code === "hardware_lease");
  const onboarding = catalog.fees.find((fee) => fee.code === "onboarding");
  const annual = catalog.cycles.find((cycle) => cycle.code === "ANNUAL");
  const registers = plan.included_registers * stores;
  let saving: number | null = null;
  let paybackMonths: number | null = null;
  if (annual && annual.months > 0) {
    const list = plan.monthly_fils * annual.months * stores;
    const paid = cycleAmount(plan.monthly_fils, annual.months, annual.discount_bps) * stores;
    saving = list - paid;
    const perMonth = saving / annual.months;
    if (onboarding && perMonth > 0) paybackMonths = (onboarding.amount_fils * stores) / perMonth;
  }
  return {
    registers,
    software: plan.monthly_fils * stores,
    lease: hardware ? hardware.monthly_fils * registers : null,
    deposit: hardware && hardware.one_time_fils > 0 ? hardware.one_time_fils * registers : null,
    saving,
    paybackMonths,
    discountPercent: annual ? annual.discount_bps / 100 : null,
    cycleName: annual?.name ?? null,
    onboarding: onboarding?.amount_fils ?? null,
  };
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
  return {
    code: value.code,
    name: value.name,
    description: typeof value.description === "string" ? value.description : "",
    monthly_fils: value.monthly_fils,
    one_time_fils: value.one_time_fils,
    refundable: value.refundable === true,
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
  if (plans.length === 0) return null;
  return { plans, cycles, addons, fees };
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
