import { acceptBusinessSettings, addonSearchScore, rankAddons, type BillingAddon, type BusinessSettings } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

function settings(patch: Partial<BusinessSettings> = {}): BusinessSettings {
  return {
    currency: "AED",
    supported_currencies: ["AED"],
    updated_at: "2026-10-29T00:00:00Z",
    updated_by_name: null,
    entitlement_revision: 4,
    capabilities: ["promotions", "gift_cards"],
    planned_capabilities: [],
    purchased_capabilities: [],
    business_profile: "retail_fashion",
    ...patch,
  };
}

function addon(patch: Partial<BillingAddon> & Pick<BillingAddon, "name" | "description">): BillingAddon {
  return {
    id: patch.name,
    code: patch.name.toLowerCase().replace(/\s+/g, "_"),
    monthly_fils: 0,
    one_time_fils: 0,
    refundable: false,
    active: true,
    module_keys: [],
    sort_order: 10,
    ...patch,
  };
}

describe("acceptBusinessSettings", () => {
  it("keeps a newer save when an older settings poll arrives", () => {
    const saved = settings({ entitlement_revision: 6, updated_at: "2026-10-29T00:01:00Z", capabilities: ["gift_cards"] });
    const stale = settings({ entitlement_revision: 5, updated_at: "2026-10-29T00:00:00Z", capabilities: ["promotions", "gift_cards"] });
    expect(acceptBusinessSettings(saved, stale)).toBe(false);
  });

  it("accepts a module change when the revision and timestamp did not move", () => {
    const current = settings();
    const next = settings({ capabilities: ["gift_cards"] });
    expect(acceptBusinessSettings(current, next)).toBe(true);
  });

  it("accepts a higher revision even when the timestamp is older", () => {
    const current = settings({ entitlement_revision: 4, updated_at: "2026-10-29T00:02:00Z" });
    const next = settings({ entitlement_revision: 5, updated_at: "2026-10-29T00:01:00Z", capabilities: ["gift_cards"] });
    expect(acceptBusinessSettings(current, next)).toBe(true);
  });

  it("ignores an identical snapshot", () => {
    const current = settings();
    expect(acceptBusinessSettings(current, settings())).toBe(false);
  });
});

describe("rankAddons", () => {
  const library = [
    addon({
      name: "Loyalty points",
      description: "Earn and redeem points on every sale.",
      sort_order: 1,
    }),
    addon({
      name: "Gift cards",
      description: "Sell gift cards at the till and accept them as payment.",
      sort_order: 3,
    }),
    addon({
      name: "Integrated card terminals",
      description: "Send the amount to the card machine.",
      sort_order: 2,
    }),
  ];

  it("lists catalogue order when the search is empty", () => {
    expect(rankAddons(library, "  ").map((row) => row.name)).toEqual([
      "Loyalty points",
      "Integrated card terminals",
      "Gift cards",
    ]);
  });

  it("ranks a name match ahead of a description match", () => {
    const ranked = rankAddons(library, "gift");
    expect(ranked.map((row) => row.name)).toEqual(["Gift cards"]);
    expect(addonSearchScore(library[1]!, "gift")).toBeGreaterThan(addonSearchScore(library[0]!, "points"));
  });

  it("matches a phrase across the name and keeps the closest name first", () => {
    const ranked = rankAddons(library, "card");
    expect(ranked[0]?.name).toBe("Integrated card terminals");
    expect(ranked.map((row) => row.name)).toContain("Gift cards");
    expect(ranked.map((row) => row.name)).not.toContain("Loyalty points");
  });

  it("matches words in the description when the name does not contain them", () => {
    expect(rankAddons(library, "every sale").map((row) => row.name)).toEqual(["Loyalty points"]);
  });
});
