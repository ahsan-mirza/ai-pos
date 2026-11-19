import { BusinessProfile, Capability, Permission } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { canOpenInventory, inventoryTabs } from "./tabs";

const manager = [
  Permission.PortalAccess,
  Permission.PortalInventoryManage,
  Permission.PortalPricingManage,
  Permission.InventoryAdjustStock,
  Permission.ReplenishmentManage,
];

const cashier = [Permission.PosAccess, Permission.PosCreditSale];

function ids(profile: (typeof BusinessProfile)[keyof typeof BusinessProfile], enabled: string[] = []) {
  return inventoryTabs(profile, new Set(enabled), manager).map((tab) => tab.id);
}

describe("inventory workspace tabs", () => {
  it("hides the workspace from a cashier", () => {
    for (const profile of Object.values(BusinessProfile)) {
      expect(canOpenInventory(profile, new Set([Capability.SerialTracking, Capability.Fefo, Capability.Recipes]), cashier)).toBe(false);
      expect(inventoryTabs(profile, new Set([Capability.SerialTracking]), cashier)).toEqual([]);
    }
  });

  it("follows the grocery profile and keeps FEFO", () => {
    expect(ids(BusinessProfile.Grocery, [Capability.Fefo])).toEqual([
      "stock",
      "products",
      "pricing",
      "price-lists",
      "price-changes",
      "categories",
      "brands",
      "units",
      "batches",
      "expiry",
      "replenishment",
      "counts",
      "purchase-orders",
      "transfers",
    ]);
    expect(ids(BusinessProfile.Grocery)).not.toContain("expiry");
    expect(ids(BusinessProfile.Grocery, [Capability.SerialTracking])).not.toContain("serials");
  });

  it("shows models and IMEI only where that capability is configured", () => {
    expect(ids(BusinessProfile.ElectronicsWholesale, [Capability.SerialTracking])).toContain("models");
    expect(ids(BusinessProfile.ElectronicsWholesale, [Capability.SerialTracking])).toContain("serials");
    expect(ids(BusinessProfile.ElectronicsWholesale)).not.toContain("serials");
    expect(ids(BusinessProfile.WholesaleRetail)).toContain("models");
    expect(ids(BusinessProfile.WholesaleRetail)).not.toContain("serials");
    expect(ids(BusinessProfile.RetailFashion, [Capability.SerialTracking, Capability.VariantsMatrix])).not.toContain("serials");
    expect(ids(BusinessProfile.RetailFashion)).not.toContain("models");
    expect(ids(BusinessProfile.RetailFashion)).not.toContain("batches");
  });

  it("uses recipe stock for food profiles and leaves IMEI off", () => {
    for (const profile of [BusinessProfile.Restaurant, BusinessProfile.Cafe, BusinessProfile.QuickService]) {
      expect(ids(profile, [Capability.Recipes])).toContain("recipes");
      expect(ids(profile, [Capability.SerialTracking])).not.toContain("serials");
      expect(ids(profile)).not.toContain("recipes");
    }
  });

  it("keeps pharmacy on the lot lifecycle and off generic batch tools", () => {
    const tabs = ids(BusinessProfile.Pharmacy, [Capability.Fefo, Capability.PharmacyCatalog, Capability.SerialTracking]);
    expect(tabs).toEqual([
      "products",
      "categories",
      "stock",
      "lots",
      "expiry",
      "purchase-orders",
      "transfers",
      "supplier-returns",
      "recalls",
      "quarantine",
      "release",
    ]);
  });

  it("drops pricing tabs when the user cannot view or manage prices", () => {
    const stockOnly = inventoryTabs(
      BusinessProfile.Grocery,
      new Set([Capability.Fefo]),
      [Permission.InventoryAdjustStock],
    ).map((tab) => tab.id);
    expect(stockOnly).toEqual(["counts"]);
  });
});
