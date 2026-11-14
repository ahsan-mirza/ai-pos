import type { BillingPlan, BillingQuote, MarketplaceItem } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import {
  addonNextStep,
  addonPriceView,
  aiAllowanceView,
  differingFeatures,
  planPriceView,
  selectorDiscountBps,
  addonIndex,
  capabilityGroups,
  changeNextAction,
  changeStatusLabel,
  comparisonCell,
  featureRecommendation,
  planChangeIsOpen,
  planLimitCell,
  presentUsage,
  upgradeRecommendation,
  usageMetricViews,
  type UsagePayload,
} from "./display";

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

function item(partial: Partial<MarketplaceItem> & Pick<MarketplaceItem, "state">): MarketplaceItem {
  return {
    reason: "",
    invoice_id: null,
    compatible_labels: [],
    search_text: "",
    addon: {
      id: "addon",
      code: "extra_register",
      name: "Extra register",
      description: "Another register",
      monthly_fils: 0,
      one_time_fils: 0,
      refundable: false,
      active: true,
      module_keys: [],
      sort_order: 0,
      ...partial.addon,
    },
    ...partial,
  };
}

function quote(partial: Partial<BillingQuote>): BillingQuote {
  return {
    currency: "AED",
    plan_code: "GROWTH",
    plan_name: "Growth",
    cycle_code: "ANNUAL",
    cycle_name: "Annual",
    months: 12,
    discount_bps: 2000,
    included_registers: 2,
    lines: [],
    recurring_fils: 123840,
    one_time_fils: 0,
    total_fils: 123840,
    ...partial,
  };
}

describe("addon prices", () => {
  it("does not present an unpriced add-on as free", () => {
    expect(addonPriceView(item({ state: "unpriced" }), "AED")).toEqual({ kind: "unpriced" });
    expect(addonPriceView(item({ state: "available" }), "AED")).toEqual({ kind: "unpriced" });
    expect(addonNextStep(item({ state: "unpriced" }), null)).toMatchObject({ type: "text", label: "Contact administrator" });
  });

  it("keeps a real monthly price and a deposit distinct", () => {
    const view = addonPriceView(
      item({
        state: "available",
        addon: {
          id: "lease",
          code: "hardware_lease",
          name: "Hardware lease",
          description: "",
          monthly_fils: 15000,
          one_time_fils: 50000,
          refundable: true,
          active: true,
          module_keys: [],
          sort_order: 1,
        },
      }),
      "AED",
    );
    expect(view.kind).toBe("priced");
    if (view.kind === "priced") {
      expect(view.lines.map((line) => line.cadence)).toEqual(["month", "deposit"]);
      expect(view.discountBps).toBeNull();
    }
  });

  it("does not call an included zero-price add-on unpriced", () => {
    expect(addonPriceView(item({ state: "included" }), "AED").kind).toBe("none");
  });
});

describe("plan prices", () => {
  it("uses the quote total and the quote discount", () => {
    const view = planPriceView({
      plan: plan({ code: "GROWTH", name: "Growth", monthly_fils: 12900 }),
      quote: quote({ discount_bps: 2000, total_fils: 123840 }),
      currency: "AED",
      pending: false,
    });
    expect(view).toMatchObject({ kind: "priced", discountBps: 2000 });
    if (view.kind === "priced") expect(view.lines[0]?.fils).toBe(123840);
  });

  it("keeps the package charge and the onboarding fee on separate lines", () => {
    const view = planPriceView({
      plan: plan({ code: "GROWTH", name: "Growth", monthly_fils: 12900 }),
      quote: quote({
        cycle_code: "MONTHLY",
        cycle_name: "Monthly",
        months: 1,
        discount_bps: 0,
        lines: [
          { code: "GROWTH", label: "Growth", quantity: 1, unit_fils: 12900, amount_fils: 12900, recurring: true, refundable: false },
          { code: "onboarding", label: "Onboarding", quantity: 1, unit_fils: 25000, amount_fils: 25000, recurring: false, refundable: false },
        ],
        recurring_fils: 12900,
        one_time_fils: 25000,
        total_fils: 37900,
      }),
      currency: "AED",
      pending: false,
    });
    expect(view.kind).toBe("priced");
    if (view.kind === "priced") {
      expect(view.lines.map((line) => [line.fils, line.cadence])).toEqual([
        [12900, "cycle"],
        [25000, "once"],
      ]);
    }
  });

  it("shows a zero free-plan price without calling it unpriced", () => {
    const view = planPriceView({
      plan: plan({ code: "FREE", name: "Free", monthly_fils: 0 }),
      currency: "AED",
      pending: false,
    });
    expect(view.kind).toBe("priced");
    if (view.kind === "priced") expect(view.lines[0]?.fils).toBe(0);
  });

  it("keeps enterprise on custom pricing", () => {
    expect(
      planPriceView({
        plan: plan({ code: "ENTERPRISE", name: "Enterprise", custom_pricing: true }),
        currency: "AED",
        pending: false,
      }).kind,
    ).toBe("custom");
  });
});

describe("billing period hint", () => {
  it("uses the published annual policy for the annual control and the cycle rate otherwise", () => {
    expect(selectorDiscountBps({ code: "ANNUAL", discount_bps: 2500 }, 2000)).toBe(2000);
    expect(selectorDiscountBps({ code: "QUARTERLY", discount_bps: 500 }, 2000)).toBe(500);
    expect(selectorDiscountBps({ code: "ANNUAL", discount_bps: 2500 }, 0)).toBe(2500);
  });
});

describe("usage metrics", () => {
  const free = plan({
    code: "FREE",
    name: "Free",
    included_registers: 1,
    resource_limits: { branches: 1, registers: 1, staff: 2, products: 500, customers: 500, ai_questions_per_month: 10 },
  });

  it("shows the cap and leaves usage unavailable when no count exists", () => {
    const rows = usageMetricViews(free);
    expect(rows.map((row) => row.key)).toEqual(["branches", "registers", "staff", "products", "customers"]);
    expect(rows.every((row) => row.state === "unavailable" && row.used === null)).toBe(true);
    expect(rows.find((row) => row.key === "products")?.limit).toBe(500);
  });

  it("draws a known count only when one is supplied", () => {
    const products = usageMetricViews(free, { products: 125 }).find((row) => row.key === "products");
    expect(products).toMatchObject({ state: "known", used: 125, limit: 500 });
  });

  it("treats a null cap as unlimited and zero as no capacity", () => {
    const enterprise = plan({
      code: "ENTERPRISE",
      name: "Enterprise",
      included_registers: 1,
      resource_limits: { branches: null, registers: null, staff: null, products: 0, customers: null },
    });
    const rows = usageMetricViews(enterprise);
    expect(rows.find((row) => row.key === "branches")?.state).toBe("unlimited");
    expect(rows.find((row) => row.key === "products")?.state).toBe("zero");
  });

  it("keeps the AI allowance out of the usage cards", () => {
    expect(usageMetricViews(free).some((row) => row.key === "products" && row.label === "AI questions")).toBe(false);
    expect(aiAllowanceView(free)).toEqual({ state: "configured", value: 10 });
    expect(aiAllowanceView(plan({ code: "LITE", name: "Lite" }))).toEqual({ state: "absent" });
  });
});

function usagePayload(overrides: Partial<UsagePayload["metrics"]["products"]> = {}): UsagePayload {
  const metric = {
    label: "Products",
    used: 2,
    limit: 5,
    available: 3,
    percentage: 40,
    status: "available" as const,
    usage_available: true,
    exceeded: false,
    ...overrides,
  };
  return {
    plan_code: "FREE",
    measured_at: "2026-11-14T08:00:00Z",
    metrics: { products: metric },
  };
}

describe("usage endpoint presentation", () => {
  it("does not turn a missing count into zero", () => {
    const products = presentUsage(usagePayload({ used: null, usage_available: false, status: "unavailable" })).find((row) => row.key === "products");
    expect(products).toMatchObject({ state: "unavailable", used: null });
  });

  it("keeps an unlimited count without a percentage", () => {
    const products = presentUsage(usagePayload({ status: "unlimited", used: 1250, limit: null, percentage: null })).find((row) => row.key === "products");
    expect(products).toMatchObject({ state: "unlimited", used: 1250, limit: null });
  });

  it("marks a reached cap without hiding the real count", () => {
    const products = presentUsage(usagePayload({ used: 6, limit: 5, status: "limit_reached", exceeded: true, percentage: 100, available: 0 })).find(
      (row) => row.key === "products",
    );
    expect(products).toMatchObject({ state: "known", used: 6, limit: 5, tone: "limit", exceeded: true });
  });

  it("recommends a catalog plan with a higher cap and no price", () => {
    const metrics = presentUsage(usagePayload({ used: 5, limit: 5, status: "limit_reached", exceeded: false, percentage: 100, available: 0 }));
    const plans = [
      plan({ code: "FREE", name: "Free", sort_order: 1, resource_limits: { products: 5 } }),
      plan({ code: "LITE", name: "Lite", sort_order: 2, catalog_family: "legacy", resource_limits: { products: 50 } }),
      plan({ code: "GROWTH", name: "Growth", sort_order: 3, monthly_fils: 12900, resource_limits: { products: 5000 } }),
      plan({ code: "ENTERPRISE", name: "Enterprise", sort_order: 9, custom_pricing: true, resource_limits: { products: null } }),
    ];
    const visible = plans.filter((row) => row.catalog_family !== "legacy");
    const suggestion = upgradeRecommendation(metrics, visible, "FREE");
    expect(suggestion?.plan.code).toBe("GROWTH");
    expect(suggestion?.contact).toBe(false);
    expect(suggestion && "price" in suggestion).toBe(false);
  });

  it("separates included, purchased, trial, and overridden capabilities", () => {
    const groups = capabilityGroups(
      [
        { feature_key: "pos", label: "POS", state: "INCLUDED" },
        { feature_key: "reach", label: "Reach", state: "INCLUDED" },
        { feature_key: "insights", label: "Insights", state: "TRIAL_INCLUDED" },
        { feature_key: "tables", label: "Tables", state: "SWITCHED_OFF" },
        { feature_key: "fx", label: "Foreign currency", state: "FEATURE_DISABLED" },
        { feature_key: "wholesale", label: "Wholesale", state: "PLUGIN_REQUIRED" },
      ],
      new Set(["reach"]),
      ["AxizReach"],
    );
    expect(groups.included).toEqual(["POS"]);
    expect(groups.purchased).toEqual(["AxizReach"]);
    expect(groups.trial).toEqual(["Insights"]);
    expect(groups.unavailable).toEqual(["Foreign currency"]);
    expect(groups.included).not.toContain("Tables");
    expect(groups.included).not.toContain("Wholesale");
  });
});

describe("plan comparison cells", () => {
  const free = plan({ code: "FREE", name: "Free", included_modules: [] });
  const growth = plan({ code: "GROWTH", name: "Growth", included_modules: ["promotions"], resource_limits: { products: 5000, customers: null } });
  const enterprise = plan({ code: "ENTERPRISE", name: "Enterprise", custom_pricing: true, included_modules: [] });
  const feature = { feature_key: "promotions", label: "Promotions", state: "UPGRADE_REQUIRED", plugin_code: null };

  it("reads included, add-on, purchased, trial, missing, unpriced, and custom from the catalog", () => {
    const priced = addonIndex([item({ state: "available", addon: { ...item({ state: "available" }).addon, code: "promo", module_keys: ["promotions"], monthly_fils: 1900 } })]);
    expect(comparisonCell(growth, feature, { currentCode: "FREE", ...priced })).toBe("included");
    expect(comparisonCell(free, feature, { currentCode: "FREE", ...priced })).toBe("addon");
    const bought = addonIndex([item({ state: "activated", addon: { ...item({ state: "activated" }).addon, module_keys: ["promotions"], monthly_fils: 1900 } })]);
    expect(comparisonCell(free, feature, { currentCode: "FREE", ...bought })).toBe("purchased");
    expect(comparisonCell(growth, feature, { currentCode: "FREE", ...bought })).toBe("included");
    const waiting = addonIndex([item({ state: "pending_payment", addon: { ...item({ state: "pending_payment" }).addon, module_keys: ["promotions"], monthly_fils: 1900 } })]);
    expect(comparisonCell(free, feature, { currentCode: "FREE", ...waiting })).toBe("addon");
    expect(waiting.purchasedKeys.has("promotions")).toBe(false);
    expect(comparisonCell(free, { ...feature, state: "TRIAL_INCLUDED" }, { currentCode: "FREE", purchasedKeys: new Set(), addons: new Map() })).toBe("trial");
    expect(comparisonCell(growth, { ...feature, state: "TRIAL_INCLUDED" }, { currentCode: "FREE", purchasedKeys: new Set(), addons: new Map() })).toBe("included");
    const unpriced = addonIndex([item({ state: "unpriced", addon: { ...item({ state: "unpriced" }).addon, module_keys: ["promotions"], monthly_fils: 0, one_time_fils: 0 } })]);
    expect(comparisonCell(free, feature, { currentCode: "FREE", ...unpriced })).toBe("unconfigured");
    expect(comparisonCell(enterprise, feature, { currentCode: "FREE", purchasedKeys: new Set(), addons: new Map() })).toBe("custom");
    expect(comparisonCell(free, { feature_key: "tables", label: "Tables", state: "SWITCHED_OFF", plugin_code: null })).toBe("absent");
    const preset = { feature_key: "loyalty", label: "Loyalty", state: "INCLUDED", plugin_code: null, baseline: true };
    expect(comparisonCell(free, preset)).toBe("included");
    expect(comparisonCell(growth, preset)).toBe("included");
    expect(comparisonCell(enterprise, preset)).toBe("custom");
    const legacy = plan({ code: "STANDARD", name: "Standard", catalog_family: "legacy", included_modules: [] });
    const kept = { feature_key: "ai_insights", label: "AI insights", state: "INCLUDED", plugin_code: null, grandfathered: true };
    expect(comparisonCell(legacy, kept, { currentCode: "STANDARD", purchasedKeys: new Set(), addons: new Map() })).toBe("included");
    expect(comparisonCell(free, kept, { currentCode: "STANDARD", purchasedKeys: new Set(), addons: new Map() })).toBe("absent");
    const insights = { feature_key: "ai_insights", label: "AI insights", state: "TRIAL_INCLUDED", plugin_code: null };
    const unpricedInsights = addonIndex([
      item({ state: "unpriced", addon: { ...item({ state: "unpriced" }).addon, module_keys: ["ai_insights"], monthly_fils: 0, one_time_fils: 0 } }),
    ]);
    const claimed = { currentCode: "FREE", ...unpricedInsights, claimedKeys: new Set(["ai_insights"]) };
    expect(comparisonCell(free, insights, claimed)).toBe("trial");
    expect(comparisonCell(growth, insights, claimed)).toBe("absent");
    expect(comparisonCell(plan({ code: "PRO_AI", name: "Pro AI", included_modules: ["ai_insights"] }), insights, claimed)).toBe("included");
    expect(comparisonCell(enterprise, insights, claimed)).toBe("custom");
  });

  it("keeps a missing cap unconfigured and a null cap unlimited", () => {
    expect(planLimitCell(growth, "products")).toEqual({ state: "configured", value: 5000 });
    expect(planLimitCell(growth, "customers")).toEqual({ state: "unlimited" });
    expect(planLimitCell(growth, "branches")).toEqual({ state: "unconfigured" });
    expect(planLimitCell(plan({ code: "FREE", name: "Free", included_registers: 1, resource_limits: {} }), "registers")).toEqual({ state: "configured", value: 1 });
  });

  it("recommends a plan only when that plan includes the feature", () => {
    const rows = [
      { feature_key: "promotions", label: "Promotions", state: "UPGRADE_REQUIRED", plugin_code: null },
      { feature_key: "reach", label: "Reach", state: "PLUGIN_REQUIRED", plugin_code: "REACH", plugin_name: "AxizReach" },
    ];
    const context = { currentCode: "FREE", purchasedKeys: new Set<string>(), addons: new Map([["reach", { priced: true }]]) };
    expect(featureRecommendation(rows, [free, growth, enterprise], context)).toMatchObject({ kind: "plan", feature: "Promotions", contact: false });
    const onlyCustom = featureRecommendation(
      [{ feature_key: "fleet", label: "Fleet", state: "UPGRADE_REQUIRED", plugin_code: null }],
      [free, plan({ code: "ENTERPRISE", name: "Enterprise", custom_pricing: true, included_modules: ["fleet"] })],
      context,
    );
    expect(onlyCustom).toMatchObject({ kind: "plan", contact: true });
    expect(featureRecommendation([{ feature_key: "missing", label: "Missing", state: "UPGRADE_REQUIRED", plugin_code: null }], [free, growth], context)).toBeNull();
  });
});

describe("comparison differences", () => {
  it("hides a feature that is identical on every visible plan", () => {
    const plans = [
      plan({ code: "FREE", name: "Free", included_modules: [] }),
      plan({ code: "GROWTH", name: "Growth", included_modules: ["promotions"] }),
    ];
    const rows = [
      { feature_key: "promotions", label: "Promotions", state: "UPGRADE_REQUIRED", plugin_code: null },
      { feature_key: "tables", label: "Tables", state: "PLUGIN_REQUIRED", plugin_code: null },
    ];
    expect(differingFeatures(rows, plans).map((row) => row.feature_key)).toEqual(["promotions"]);
  });
});

describe("plan change status", () => {
  it("keeps a pending request distinct from the active plan", () => {
    expect(changeStatusLabel("pending_payment")).toBe("Awaiting payment");
    expect(changeStatusLabel("payment_submitted")).toBe("Payment proof submitted");
    expect(changeStatusLabel("completed")).toBe("Completed");
    expect(changeNextAction("pending_payment", "The slip is unreadable.")).toBe("Submit a corrected payment proof.");
    expect(changeNextAction("quoted", null)).toBe("Generate the invoice to continue.");
    expect(planChangeIsOpen("quoted")).toBe(true);
    expect(planChangeIsOpen("completed")).toBe(false);
    expect(planChangeIsOpen("cancelled")).toBe(false);
  });
});

describe("add-on actions", () => {
  it("keeps purchase, open, invoice, and review on the existing destinations", () => {
    expect(addonNextStep(item({ state: "available", addon: { ...item({ state: "available" }).addon, monthly_fils: 4900 } }), null).type).toBe("purchase");
    expect(addonNextStep(item({ state: "activated" }), "/inventory")).toMatchObject({ type: "link", href: "/inventory", label: "Open" });
    expect(addonNextStep(item({ state: "pending_payment" }), null)).toMatchObject({ href: "/subscription", label: "View invoice" });
    expect(addonNextStep(item({ state: "expired" }), null)).toMatchObject({ href: "/subscription", label: "Review subscription" });
    expect(addonNextStep(item({ state: "unavailable", reason: "Not available for Restaurant businesses." }), null)).toMatchObject({
      translate: false,
      label: "Not available for Restaurant businesses.",
    });
  });
});
