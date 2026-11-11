import type { BillingPlan } from "@ai-pos/shared-types";

const CURRENT_CODES = new Set(["FREE", "GROWTH", "PRO_AI", "ENTERPRISE"]);

export function planFamily(plan: BillingPlan): "current" | "legacy" {
  if (plan.catalog_family === "current" || plan.catalog_family === "legacy") return plan.catalog_family;
  return CURRENT_CODES.has(plan.code) ? "current" : "legacy";
}

/** Current catalog, plus a legacy plan only when this store is already on it. */
export function visiblePlans(plans: readonly BillingPlan[], currentCode: string | null): BillingPlan[] {
  return plans
    .filter((plan) => plan.active)
    .filter((plan) => planFamily(plan) === "current" || plan.code === currentCode)
    .sort((left, right) => left.sort_order - right.sort_order || left.name.localeCompare(right.name));
}

export function isCustomPlan(plan: BillingPlan): boolean {
  return plan.custom_pricing === true || plan.code === "ENTERPRISE";
}

export function isFreePlan(plan: BillingPlan): boolean {
  return plan.code === "FREE";
}

export type ComparisonMark = "included" | "plugin" | "absent";

/** A cell in the comparison. Plugin means the catalogue sells it separately, not inside this plan. */
export function comparisonMark(plan: BillingPlan, featureKey: string, pluginCode: string | null): ComparisonMark {
  if (plan.included_modules.includes(featureKey)) return "included";
  if (pluginCode) return "plugin";
  return "absent";
}

/** Restaurant-only and unpublished capabilities stay out of the table for a store that cannot buy them. */
export function comparableFeature(state: string): boolean {
  return state !== "BUSINESS_TYPE_UNAVAILABLE" && state !== "COUNTRY_UNAVAILABLE" && state !== "FEATURE_DISABLED";
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

export interface PlanLimit {
  key: string;
  label: string;
  value: number;
  unit: string;
}

/** Configured caps only. There is no usage count on the billing APIs, so these are not progress bars. */
export function planLimits(plan: BillingPlan | undefined): PlanLimit[] {
  if (!plan) return [];
  const rows: PlanLimit[] = [];
  if (plan.included_registers > 0) {
    rows.push({ key: "included_registers", label: "Registers", value: plan.included_registers, unit: "included" });
  }
  const limits = plan.resource_limits ?? {};
  for (const [key, value] of Object.entries(limits)) {
    if (typeof value !== "number") continue;
    if (key === "registers") continue;
    rows.push({
      key,
      label: LIMIT_LABELS[key] ?? key,
      value,
      unit: key === "sales_history_days" ? "days" : "included",
    });
  }
  return rows;
}
