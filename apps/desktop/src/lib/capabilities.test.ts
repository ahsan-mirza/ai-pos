import {
  CAPABILITIES,
  PROFILE_PRESETS,
  missingDependencies,
  profileSpec,
  resolveCapabilities,
  type BusinessProfile,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { applyProfile, applySignedInAddons, bindCapabilityTenant, capabilityCacheKey, registerCapabilities } from "./capabilities";

const SCOPE = { tenantId: "electronics", environment: "http://127.0.0.1:18080" };

function memoryStorage() {
  const values = new Map<string, string>();
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    },
  });
  return values;
}

describe("business profiles", () => {
  it("ships the business presets and keeps food and beverage at three", () => {
    expect(Object.keys(PROFILE_PRESETS).sort()).toEqual(
      ["cafe", "electronics_wholesale", "grocery", "laundry", "pharmacy", "quick_service", "restaurant", "retail_fashion", "wholesale_retail"].sort(),
    );
    const groups = Object.values(PROFILE_PRESETS).map((profile) => profile.group);
    expect(groups.filter((group) => group === "food_beverage")).toHaveLength(3);
  });

  it("gives electronics & wholesale its retail-trade modules, never grocery or restaurant ones", () => {
    const { enabled, planned } = resolveCapabilities("electronics_wholesale");
    expect(enabled).toEqual(PROFILE_PRESETS.electronics_wholesale.capabilities);
    expect(enabled).not.toContain("fefo");
    expect(enabled.every((id) => CAPABILITIES.find((spec) => spec.id === id)?.group !== "food_beverage")).toBe(true);
    expect(planned).toEqual([]);
  });

  it("enables shipped F&B modules and keeps the rest planned", () => {
    for (const profile of ["restaurant", "cafe", "quick_service"] as BusinessProfile[]) {
      const { enabled, planned } = resolveCapabilities(profile);
      const shipped = (id: string) => CAPABILITIES.find((spec) => spec.id === id)?.available === true;
      expect(enabled).toContain("loyalty");
      expect(enabled.every(shipped)).toBe(true);
      expect(planned.some(shipped)).toBe(false);
      expect(enabled).not.toContain("serial_tracking");
    }
    expect(resolveCapabilities("cafe").planned).not.toContain("tables");
    expect(resolveCapabilities("cafe").enabled).not.toContain("tables");
  });

  it("drops capabilities whose prerequisites are missing", () => {
    expect(missingDependencies(["quotes_layaway"])).toEqual([]);
    expect(missingDependencies(["recipes"])).toEqual([{ capability: "recipes", missing: ["menu_modifiers"] }]);
    expect(resolveCapabilities("cafe", ["recipes", "kds"]).enabled).toEqual(["kds"]);
    expect(missingDependencies(["tables", "open_orders"])).toEqual([]);
  });

  it("ignores unknown ids in a stored selection", () => {
    expect(resolveCapabilities("grocery", ["loyalty", "teleportation"]).enabled).toEqual(["loyalty"]);
  });

  it("has a valid preset for every profile", () => {
    for (const profile of Object.values(PROFILE_PRESETS)) {
      expect(missingDependencies(profile.capabilities)).toEqual([]);
    }
  });

  it("names the business-wide settings after the business type", () => {
    for (const profile of Object.values(PROFILE_PRESETS)) {
      expect(profile.shortLabel.trim()).not.toBe("");
      expect(profile.settingsLabel).toMatch(/ settings$/);
    }
    expect(profileSpec("retail_fashion").settingsLabel).toBe("Store settings");
    expect(profileSpec("restaurant").settingsLabel).toBe("Restaurant settings");
    expect(profileSpec("cafe").settingsLabel).toBe("Cafe settings");
    expect(profileSpec("teleportation").id).toBe("electronics_wholesale");
    expect(profileSpec(null).shortLabel).toBe("Electronics");
  });

  it("keeps the newer entitlement and drops a purchase after its offline window", () => {
    memoryStorage();
    bindCapabilityTenant(SCOPE);
    applyProfile({
      tenant_id: SCOPE.tenantId,
      environment: SCOPE.environment,
      business_profile: "electronics_wholesale",
      capabilities: ["loyalty"],
      entitlement_revision: 2,
      purchased_capabilities: [],
      entitlement_until: null,
    });
    expect(registerCapabilities().enabled.has("loyalty")).toBe(true);
    applyProfile({
      tenant_id: SCOPE.tenantId,
      environment: SCOPE.environment,
      business_profile: "electronics_wholesale",
      capabilities: ["promotions"],
      entitlement_revision: 1,
    });
    expect(registerCapabilities().enabled.has("loyalty")).toBe(true);
    applyProfile({
      tenant_id: SCOPE.tenantId,
      environment: SCOPE.environment,
      business_profile: "electronics_wholesale",
      capabilities: ["loyalty", "sales_orders"],
      entitlement_revision: 3,
      purchased_capabilities: ["sales_orders"],
      entitlement_until: new Date(Date.now() - 60_000).toISOString(),
    });
    expect(registerCapabilities().enabled.has("loyalty")).toBe(true);
    expect(registerCapabilities().enabled.has("sales_orders")).toBe(false);
  });

  it("hides a paid add-on from a cashier who was not granted it, including a stale offline unlock", () => {
    memoryStorage();
    bindCapabilityTenant(SCOPE);
    applyProfile({
      tenant_id: SCOPE.tenantId,
      environment: SCOPE.environment,
      business_profile: "electronics_wholesale",
      capabilities: ["loyalty", "gift_cards"],
      entitlement_revision: 4,
      purchased_capabilities: ["gift_cards"],
      entitlement_until: new Date(Date.now() + 86_400_000).toISOString(),
    });
    applySignedInAddons(["gift_cards"], { offline: false, syncedAt: 1_000, now: 1_100 });
    expect(registerCapabilities().enabled.has("gift_cards")).toBe(true);
    expect(registerCapabilities().enabled.has("loyalty")).toBe(true);
    applySignedInAddons([], { offline: false, syncedAt: 1_000, now: 1_100 });
    expect(registerCapabilities().enabled.has("gift_cards")).toBe(false);
    expect(registerCapabilities().enabled.has("loyalty")).toBe(true);
    applySignedInAddons(["gift_cards"], { offline: true, syncedAt: 1_000, now: 1_000 + 24 * 60 * 60 + 5 });
    expect(registerCapabilities().enabled.has("gift_cards")).toBe(false);
    applySignedInAddons(null);
  });

  it("accepts a grocery snapshot whose revision is lower than the previous tenant", () => {
    const values = memoryStorage();
    const pharmacy = { tenantId: "pharmacy-accept", environment: SCOPE.environment };
    const grocery = { tenantId: "accept-grocery", environment: SCOPE.environment };
    bindCapabilityTenant(pharmacy);
    applyProfile({
      tenant_id: pharmacy.tenantId,
      environment: pharmacy.environment,
      business_profile: "pharmacy",
      capabilities: ["pharmacy_catalog", "fefo"],
      entitlement_revision: 4,
    });
    expect(registerCapabilities().profile).toBe("pharmacy");
    expect(values.has(capabilityCacheKey(pharmacy))).toBe(true);

    bindCapabilityTenant(grocery);
    expect(registerCapabilities().available).toBe(false);
    expect(registerCapabilities().enabled.has("pharmacy_catalog")).toBe(false);
    applyProfile({
      tenant_id: grocery.tenantId,
      environment: grocery.environment,
      business_profile: "grocery",
      capabilities: ["loyalty", "fefo"],
      entitlement_revision: 3,
    });
    expect(registerCapabilities().profile).toBe("grocery");
    expect(registerCapabilities().enabled.has("pharmacy_catalog")).toBe(false);
    expect(registerCapabilities().enabled.has("fefo")).toBe(true);

    bindCapabilityTenant(pharmacy);
    expect(registerCapabilities().profile).toBe("pharmacy");
    expect(registerCapabilities().enabled.has("pharmacy_catalog")).toBe(true);
  });

  it("rejects a snapshot for another tenant, a missing identity, and the old unscoped cache", () => {
    const values = memoryStorage();
    values.set("ai-pos.register-capabilities", JSON.stringify({ business_profile: "pharmacy", capabilities: ["pharmacy_catalog"], entitlement_revision: 9 }));
    bindCapabilityTenant(SCOPE);
    expect(values.has("ai-pos.register-capabilities")).toBe(false);
    expect(registerCapabilities().available).toBe(false);
    applyProfile({ business_profile: "pharmacy", capabilities: ["pharmacy_catalog"], entitlement_revision: 4 });
    applyProfile({
      tenant_id: "someone-else",
      environment: SCOPE.environment,
      business_profile: "pharmacy",
      capabilities: ["pharmacy_catalog"],
      entitlement_revision: 9,
    });
    expect(registerCapabilities().available).toBe(false);
    values.set(capabilityCacheKey({ tenantId: SCOPE.tenantId, environment: "http://other" }), JSON.stringify({
      schema: 1,
      tenant_id: SCOPE.tenantId,
      environment: "http://other",
      business_profile: "pharmacy",
      capabilities: ["pharmacy_catalog"],
      entitlement_revision: 4,
      fetched_at: new Date().toISOString(),
    }));
    bindCapabilityTenant(SCOPE);
    expect(registerCapabilities().available).toBe(false);
  });
});
