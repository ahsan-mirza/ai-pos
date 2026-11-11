import { describe, expect, it } from "vitest";
import type { BillingPlan } from "@ai-pos/shared-types";
import { comparableFeature, comparisonMark, planLimits, visiblePlans } from "./subscriptionPlans";

function plan(partial: Partial<BillingPlan> & Pick<BillingPlan, "code" | "name">): BillingPlan {
  return {
    id: partial.code,
    included_registers: 1,
    included_modules: [],
    monthly_fils: 0,
    trial_days: 0,
    active: true,
    sort_order: 0,
    ...partial,
  };
}

describe("visiblePlans", () => {
  const plans = [
    plan({ code: "FREE", name: "Free", catalog_family: "current", sort_order: 1 }),
    plan({ code: "LITE", name: "Lite", catalog_family: "legacy", sort_order: 0 }),
    plan({ code: "GROWTH", name: "Growth", catalog_family: "current", sort_order: 2 }),
    plan({ code: "OLD", name: "Old", active: false, catalog_family: "legacy" }),
  ];

  it("hides legacy plans from a free store", () => {
    expect(visiblePlans(plans, "FREE").map((row) => row.code)).toEqual(["FREE", "GROWTH"]);
  });

  it("keeps the legacy plan a store is already on", () => {
    expect(visiblePlans(plans, "LITE").map((row) => row.code)).toEqual(["LITE", "FREE", "GROWTH"]);
  });
});

describe("comparisonMark", () => {
  const growth = plan({ code: "GROWTH", name: "Growth", included_modules: ["promotions"] });

  it("reads inclusion from the plan row", () => {
    expect(comparisonMark(growth, "promotions", null)).toBe("included");
    expect(comparisonMark(growth, "axiz_reach", "REACH")).toBe("plugin");
    expect(comparisonMark(growth, "ai_insights", null)).toBe("absent");
  });
});

describe("comparableFeature", () => {
  it("drops capabilities this business type cannot buy", () => {
    expect(comparableFeature("BUSINESS_TYPE_UNAVAILABLE")).toBe(false);
    expect(comparableFeature("UPGRADE_REQUIRED")).toBe(true);
  });
});

describe("planLimits", () => {
  it("lists configured caps and skips unset ones", () => {
    const rows = planLimits(
      plan({
        code: "FREE",
        name: "Free",
        included_registers: 1,
        resource_limits: { branches: 1, products: null, staff: 3 },
      }),
    );
    expect(rows.map((row) => `${row.label}:${row.value}`)).toEqual(["Registers:1", "Branches:1", "Staff:3"]);
  });
});
