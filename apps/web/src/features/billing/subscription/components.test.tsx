import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import type { BillingPlan, MarketplaceItem } from "@ai-pos/shared-types";
import { AddonCard } from "./AddonCard";
import { addonPriceView, planPriceView, presentUsage, usageMetricViews, type UsagePayload } from "./display";
import { PlanComparisonTable } from "./PlanComparisonTable";
import { SubscriptionSummaryCard } from "./SubscriptionSummaryCard";
import { EmptyState, ErrorState, LoadingBlock, LoadingCards } from "./States";
import { PlanCard } from "./PlanCard";
import { PriceDisplay } from "./PriceDisplay";
import { UsageMetricCard } from "./UsageMetricCard";

function plan(partial: Partial<BillingPlan> & Pick<BillingPlan, "code" | "name">): BillingPlan {
  return {
    id: partial.code,
    included_registers: 1,
    included_modules: ["promotions"],
    monthly_fils: 0,
    trial_days: 0,
    active: true,
    sort_order: 0,
    resource_limits: { products: 500 },
    ...partial,
  };
}

function unpriced(): MarketplaceItem {
  return {
    state: "unpriced",
    reason: "Set a price in the console.",
    invoice_id: null,
    compatible_labels: ["Retail"],
    search_text: "",
    addon: {
      id: "reach",
      code: "axiz_reach",
      name: "AxizReach",
      description: "Customer messages",
      monthly_fils: 0,
      one_time_fils: 0,
      refundable: false,
      active: true,
      module_keys: [],
      sort_order: 1,
    },
  };
}

describe("commercial cards", () => {
  it("renders an unpriced add-on without a free purchase", () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <AddonCard item={unpriced()} currency="AED" onPurchase={() => undefined} />
      </MemoryRouter>,
    );
    expect(html).toContain("Price not configured");
    expect(html).toContain("View details");
    expect(html).not.toContain("Learn More");
    expect(html).not.toContain("Buy Now");
    expect(html).not.toContain(">Free<");
  });

  it("renders a custom plan without a hardcoded price", () => {
    const enterprise = plan({ code: "ENTERPRISE", name: "Enterprise", custom_pricing: true, included_modules: [] });
    const html = renderToStaticMarkup(
      <PlanCard
        plan={enterprise}
        price={planPriceView({ plan: enterprise, currency: "AED", pending: false })}
        current={false}
        highlighted={false}
        legacy={false}
        trialNote={false}
        onUpgrade={() => undefined}
      />,
    );
    expect(html).toContain("Custom pricing");
    expect(html).toContain("Enterprise");
    expect(html).not.toContain("129.00");
  });

  it("shows optional onboarding assistance apart from the subscription price", () => {
    const growth = plan({ code: "GROWTH", name: "Growth", monthly_fils: 12900 });
    const html = renderToStaticMarkup(
      <PlanCard
        plan={growth}
        price={planPriceView({
          plan: growth,
          currency: "AED",
          pending: false,
          quote: {
            currency: "AED",
            plan_code: "GROWTH",
            plan_name: "Growth",
            cycle_code: "MONTHLY",
            cycle_name: "Monthly",
            months: 1,
            discount_bps: 0,
            included_registers: 2,
            lines: [
              {
                code: "GROWTH",
                label: "Growth · Monthly",
                quantity: 1,
                unit_fils: 12900,
                amount_fils: 12900,
                recurring: true,
                refundable: false,
              },
            ],
            recurring_fils: 12900,
            one_time_fils: 0,
            total_fils: 12900,
          },
        })}
        current={false}
        highlighted={false}
        legacy={false}
        trialNote={false}
        onboardingFils={25000}
        onUpgrade={() => undefined}
      />,
    );
    expect(html).toContain("129.00");
    expect(html).toContain("Optional onboarding assistance");
    expect(html).toContain("250.00");
    expect(html).toContain("What is onboarding assistance?");
  });

  it("renders a quote price and its applied discount", () => {
    const growth = plan({ code: "GROWTH", name: "Growth", monthly_fils: 12900 });
    const html = renderToStaticMarkup(
      <PriceDisplay
        view={{
          kind: "priced",
          discountBps: 2000,
          lines: [{ fils: 123840, currency: "AED", cadence: "cycle", periodName: "Annual" }],
        }}
      />,
    );
    expect(html).toContain("1,238.40");
    expect(html).toContain("<sub");
    expect(html).toContain("/ Annual");
    expect(html).toContain("20% off this cycle");
    expect(growth.code).toBe("GROWTH");
  });

  it("shows an allowance without a usage bar when consumption is unknown", () => {
    const metric = usageMetricViews(plan({ code: "FREE", name: "Free", resource_limits: { products: 500 } })).find((row) => row.key === "products");
    expect(metric).toBeDefined();
    const html = renderToStaticMarkup(<UsageMetricCard metric={metric!} />);
    expect(html).toContain("Usage unavailable");
    expect(html).toContain("500");
    expect(html).not.toContain("progressbar");
  });

  it("renders a progress bar only for a known count", () => {
    const html = renderToStaticMarkup(
      <UsageMetricCard metric={{ key: "products", label: "Products", state: "known", used: 125, limit: 500 }} />,
    );
    expect(html).toContain("progressbar");
    expect(html).toContain("125");
    expect(html).toContain("375");
  });

  it("shows an unlimited count without a bar and a reached cap with its real total", () => {
    const payload: UsagePayload = {
      plan_code: "GROWTH",
      measured_at: "2026-11-14T08:00:00Z",
      metrics: {
        products: {
          label: "Products",
          used: 1250,
          limit: null,
          available: null,
          percentage: null,
          status: "unlimited",
          usage_available: true,
          exceeded: false,
        },
        branches: {
          label: "Branches",
          used: 6,
          limit: 5,
          available: 0,
          percentage: 100,
          status: "limit_reached",
          usage_available: true,
          exceeded: true,
        },
      },
    };
    const rows = presentUsage(payload);
    const unlimited = renderToStaticMarkup(<UsageMetricCard metric={rows.find((row) => row.key === "products")!} />);
    expect(unlimited).toContain("1250");
    expect(unlimited).toContain("Unlimited");
    expect(unlimited).not.toContain("progressbar");
    const reached = renderToStaticMarkup(<UsageMetricCard metric={rows.find((row) => row.key === "branches")!} />);
    expect(reached).toContain("6");
    expect(reached).toContain("Limit reached");
    expect(reached).toContain("progressbar");
  });
});

function addon(state: MarketplaceItem["state"], key: string, monthly: number): MarketplaceItem {
  return {
    state,
    reason: "",
    invoice_id: null,
    compatible_labels: [],
    search_text: "",
    addon: {
      id: key,
      code: key,
      name: key,
      description: key,
      monthly_fils: monthly,
      one_time_fils: 0,
      refundable: false,
      active: true,
      module_keys: [key],
      sort_order: 1,
    },
  };
}

describe("plan comparison states", () => {
  const free = plan({ code: "FREE", name: "Free", included_modules: [], resource_limits: { products: 10, branches: 1 } });
  const growth = plan({ code: "GROWTH", name: "Growth", included_modules: ["promotions"], resource_limits: { products: 100, branches: 2 } });
  const enterprise = plan({ code: "ENTERPRISE", name: "Enterprise", custom_pricing: true, included_modules: [], resource_limits: { products: null } });

  it("shows a purchased add-on as purchased and a pending payment as available", () => {
    const bought = renderToStaticMarkup(
      <PlanComparisonTable
        plans={[free, growth]}
        currentCode="FREE"
        features={[{ feature_key: "tables", label: "Tables", state: "PLUGIN_REQUIRED", plugin_code: "TABLES" }]}
        items={[addon("activated", "tables", 1900)]}
      />,
    );
    expect(bought).toContain("Purchased");
    expect(bought).toContain("Add-on available");
    const waiting = renderToStaticMarkup(
      <PlanComparisonTable
        plans={[free, growth]}
        currentCode="FREE"
        features={[{ feature_key: "tables", label: "Tables", state: "PLUGIN_REQUIRED", plugin_code: "TABLES" }]}
        items={[addon("pending_payment", "tables", 1900)]}
      />,
    );
    expect(waiting).not.toContain("Purchased");
    expect(waiting).toContain("Add-on available");
  });

  it("recommends a higher cap and a plan that actually includes the feature", () => {
    const html = renderToStaticMarkup(
      <PlanComparisonTable
        plans={[free, growth, enterprise]}
        currentCode="FREE"
        features={[{ feature_key: "promotions", label: "Promotions", state: "UPGRADE_REQUIRED", plugin_code: null }]}
        usage={[{ key: "products", label: "Products", state: "known", used: 9, limit: 10, tone: "warning" }]}
      />,
    );
    expect(html).toContain("Growth includes a higher Products allowance.");
    expect(html).toContain("Promotions is included in Growth.");
    expect(html).not.toContain("Enterprise includes a higher");
  });

  it("names a retired subscription without offering that package", () => {
    const html = renderToStaticMarkup(
      <SubscriptionSummaryCard
        subscription={{ plan_name: "Lite", plan_code: "LITE", status: "active", cycle_name: "Monthly", price_fils: 14900, currency: "AED" }}
        plan={undefined}
      />,
    );
    expect(html).toContain("Lite");
    expect(html).toContain("This package is retired.");
    expect(html).toContain("stays on Lite");
  });
});

describe("subscription page states", () => {
  it("renders empty, loading, and error states without sample records", () => {
    expect(renderToStaticMarkup(<EmptyState title="No plans are published." />)).toContain("No plans are published.");
    expect(renderToStaticMarkup(<LoadingCards count={2} />)).toContain("aria-busy");
    expect(renderToStaticMarkup(<LoadingBlock />)).toContain("animate-pulse");
    expect(renderToStaticMarkup(<ErrorState message="Could not load plans." />)).toContain("Could not load plans.");
    expect(renderToStaticMarkup(<PriceDisplay view={addonPriceView(unpriced(), "AED")} />)).toContain("Price not configured");
  });
});
