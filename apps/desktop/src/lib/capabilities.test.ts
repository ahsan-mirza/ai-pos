import {
  CAPABILITIES,
  PROFILE_PRESETS,
  missingDependencies,
  profileSpec,
  resolveCapabilities,
  type BusinessProfile,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

describe("business profiles", () => {
  it("ships the six presets in two groups", () => {
    expect(Object.keys(PROFILE_PRESETS).sort()).toEqual(
      ["cafe", "electronics_wholesale", "grocery", "quick_service", "restaurant", "retail_fashion"].sort(),
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
});
