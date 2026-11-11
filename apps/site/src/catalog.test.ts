import { describe, expect, it } from "vitest";
import {
  addonPriceText,
  comparisonMark,
  comparisonRows,
  parseCatalog,
  publicPlugins,
  publishedPrice,
  type Addon,
  type Plan,
} from "./catalog";

function plan(partial: Partial<Plan> & Pick<Plan, "code" | "name" | "included_modules">): Plan {
  return {
    included_registers: 1,
    monthly_fils: 0,
    trial_days: 0,
    active: true,
    sort_order: 0,
    catalog_family: "current",
    custom_pricing: partial.code === "ENTERPRISE",
    resource_limits: {},
    prices: [],
    ...partial,
  };
}

function addon(partial: Partial<Addon> & Pick<Addon, "code" | "module_keys">): Addon {
  return {
    name: partial.code,
    description: "",
    monthly_fils: 0,
    one_time_fils: 0,
    refundable: false,
    active: true,
    sort_order: 0,
    short_description: "",
    category: "",
    featured: false,
    benefits: [],
    documentation_url: "",
    ...partial,
  };
}

describe("comparisonRows", () => {
  const plans = [
    plan({ code: "FREE", name: "Free", included_modules: ["loyalty"] }),
    plan({ code: "GROWTH", name: "Growth", included_modules: ["loyalty", "promotions"] }),
  ];

  it("lists a published add-on as its own row without calling it included", () => {
    const rows = comparisonRows(plans, [addon({ code: "REACH", module_keys: ["axiz_reach"], monthly_fils: 4900 })]);
    expect(rows.map((row) => row.key)).toEqual(["loyalty", "promotions", "axiz_reach"]);
    expect(rows.find((row) => row.key === "axiz_reach")?.pluginCodes).toEqual(["REACH"]);
    expect(comparisonMark(plans[0]!, rows[2]!)).toBe("addon");
  });

  it("hides capabilities the selected business type cannot use", () => {
    const withTables = [plan({ code: "GROWTH", name: "Growth", included_modules: ["loyalty", "tables"] })];
    expect(comparisonRows(withTables, [], "grocery").map((row) => row.key)).toEqual(["loyalty"]);
    expect(comparisonRows(withTables, [], "restaurant").map((row) => row.key)).toContain("tables");
  });
});

describe("comparisonMark", () => {
  const row = { key: "promotions", pluginCodes: ["PROMO"] };
  const free = plan({ code: "FREE", name: "Free", included_modules: [] });
  const growth = plan({ code: "GROWTH", name: "Growth", included_modules: ["promotions"] });
  const enterprise = plan({ code: "ENTERPRISE", name: "Enterprise", included_modules: [], custom_pricing: true });

  it("uses the published plan list, then an add-on, then custom, then absent", () => {
    expect(comparisonMark(growth, row)).toBe("included");
    expect(comparisonMark(free, row)).toBe("addon");
    expect(comparisonMark(enterprise, row)).toBe("addon");
    expect(comparisonMark(free, { key: "ai_insights", pluginCodes: [] })).toBe("absent");
    expect(comparisonMark(enterprise, { key: "ai_insights", pluginCodes: [] })).toBe("custom");
  });
});

describe("publishedPrice", () => {
  const cycle = { code: "MONTHLY", name: "Monthly", months: 1, discount_bps: 0 };
  const catalog = {
    plans: [],
    cycles: [cycle],
    addons: [],
    fees: [],
    hardware: [],
    current_annual_discount_bps: 2000,
    promotional_trial: { enabled: false, days: 0, plan_code: "", eligible_plans: [] },
  };

  it("does not treat an Enterprise zero as a purchase price", () => {
    const enterprise = plan({
      code: "ENTERPRISE",
      name: "Enterprise",
      included_modules: [],
      monthly_fils: 0,
      custom_pricing: true,
    });
    expect(publishedPrice(enterprise, cycle, catalog, "AE").kind).toBe("custom");
  });
});

describe("public plugins", () => {
  it("drops unpublished add-ons and prices them in AED only", () => {
    const parsed = parseCatalog({
      plans: [plan({ code: "FREE", name: "Free", included_modules: [] })],
      addons: [
        {
          code: "SERIAL",
          name: "Serial tracking",
          monthly_fils: 4900,
          one_time_fils: 0,
          module_keys: ["serial_tracking"],
          listing: { publication: "published", short_description: "Campaigns", benefits: [{ title: "Segments", description: "" }] },
        },
        { code: "HIDDEN", name: "Hidden", monthly_fils: 100, one_time_fils: 0, listing: { publication: "draft" } },
      ],
    });
    expect(parsed?.addons.map((row) => row.code)).toEqual(["SERIAL"]);
    expect(publicPlugins(parsed?.addons ?? [], "restaurant").map((row) => row.code)).toEqual([]);
    expect(publicPlugins(parsed?.addons ?? [], "electronics_wholesale").map((row) => row.code)).toEqual(["SERIAL"]);
    expect(addonPriceText(parsed!.addons[0], "AED")).toContain("month");
    expect(addonPriceText(parsed!.addons[0], "USD")).toBeNull();
  });
});
