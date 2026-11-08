/// <reference types="jest" />
import { BusinessProfile, PROFILE_PRESETS } from "@ai-pos/shared-types";
import { focusModuleIds } from "./profileFocus";

describe("business profile focus", () => {
  it("keeps electronics on serials and warranties, away from the dining floor", () => {
    const ids = focusModuleIds(PROFILE_PRESETS.electronics_wholesale.capabilities);
    expect(ids.slice(0, 4)).toEqual(["serials", "warranties", "repairs", "trade-ins"]);
    expect(ids).not.toContain("floor-plan");
    expect(ids).not.toContain("kitchen");
  });

  it("keeps wholesale on orders and pricing", () => {
    const ids = focusModuleIds(PROFILE_PRESETS.wholesale_retail.capabilities);
    expect(ids).toContain("sales-orders");
    expect(ids).toContain("pricing");
    expect(ids).not.toContain("modifiers");
  });

  it("keeps fashion on the size grid", () => {
    const ids = focusModuleIds(PROFILE_PRESETS.retail_fashion.capabilities);
    expect(ids).toContain("size-curve");
    expect(ids).not.toContain("kitchen");
    expect(ids).not.toContain("serials");
  });

  it("keeps grocery on weighed products and expiry", () => {
    const ids = focusModuleIds(PROFILE_PRESETS.grocery.capabilities);
    expect(ids).toContain("products");
    expect(ids).toContain("expiring");
    expect(ids).not.toContain("floor-plan");
  });

  it("keeps restaurant, cafe, and quick service on their own operations", () => {
    expect(focusModuleIds(PROFILE_PRESETS.restaurant.capabilities)).toEqual(expect.arrayContaining(["floor-plan", "kitchen", "modifiers"]));
    expect(focusModuleIds(PROFILE_PRESETS.cafe.capabilities)).toEqual(expect.arrayContaining(["kitchen", "modifiers"]));
    expect(focusModuleIds(PROFILE_PRESETS.cafe.capabilities)).not.toContain("floor-plan");
    expect(focusModuleIds(PROFILE_PRESETS.quick_service.capabilities)).toEqual(expect.arrayContaining(["kitchen", "modifiers", "meals", "channels"]));
    for (const profile of [BusinessProfile.Restaurant, BusinessProfile.Cafe, BusinessProfile.QuickService]) {
      expect(focusModuleIds(PROFILE_PRESETS[profile].capabilities)).not.toContain("serials");
    }
  });

  it("keeps mixed capabilities together when a tenant enables more than one trade", () => {
    const ids = focusModuleIds([
      ...PROFILE_PRESETS.electronics_wholesale.capabilities,
      ...PROFILE_PRESETS.restaurant.capabilities,
    ]);
    expect(ids).toContain("serials");
    expect(ids).toContain("floor-plan");
  });
});
