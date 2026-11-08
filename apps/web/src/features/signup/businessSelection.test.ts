import { SIGNUP_BUSINESS_CARDS } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import {
  businessMotion,
  categoryColumns,
  operatingModels,
  orderedCategories,
  selectionReady,
  setupPreview,
  subTypeAfterCategoryChange,
} from "./businessSelection";

const labels = [
  "Electronics",
  "Wholesale & Retail",
  "Retail & Fashion",
  "Supermarket",
  "Restaurant",
  "Cafe",
  "Quick Service",
];

describe("business category selection", () => {
  it("lists every supported category once", () => {
    expect(SIGNUP_BUSINESS_CARDS.map((card) => card.label)).toEqual(labels);
    expect(new Set(SIGNUP_BUSINESS_CARDS.map((card) => card.profile)).size).toBe(labels.length);
  });

  it("moves the selected category to the top without duplicating cards", () => {
    const ordered = orderedCategories("cafe");
    expect(ordered[0]?.profile).toBe("cafe");
    expect(ordered).toHaveLength(SIGNUP_BUSINESS_CARDS.length);
    expect(new Set(ordered.map((card) => card.profile)).size).toBe(SIGNUP_BUSINESS_CARDS.length);
    expect(orderedCategories(null).map((card) => card.profile)).toEqual(
      SIGNUP_BUSINESS_CARDS.map((card) => card.profile),
    );
  });

  it("uses a compact column count for phone, tablet and desktop widths", () => {
    expect(categoryColumns(360)).toBe(1);
    expect(categoryColumns(768)).toBe(2);
    expect(categoryColumns(1280)).toBe(2);
    expect(categoryColumns(1920)).toBe(2);
  });

  it("skips motion when the user prefers reduced motion", () => {
    expect(businessMotion(true).duration).toBe(0);
    expect(businessMotion(false).duration).toBeGreaterThan(0);
    expect(businessMotion(false).duration).toBeLessThanOrEqual(0.4);
  });
});

describe("operating models", () => {
  it("shows only the models for the selected category", () => {
    expect(operatingModels("cafe").map((model) => model.id)).toEqual([
      "counter_cafe",
      "sit_down_cafe",
      "bakery_cafe",
      "cafe_quick",
      "cafe_delivery",
      "cafe_all",
    ]);
    expect(operatingModels("restaurant").map((model) => model.label)).toContain("Cloud kitchen");
    expect(operatingModels("restaurant").some((model) => model.id.startsWith("grocery"))).toBe(false);
    expect(operatingModels("grocery").map((model) => model.label)).toContain("Neighborhood grocery");
    expect(operatingModels("electronics_wholesale").map((model) => model.label)).toContain("Electronics retail store");
    expect(operatingModels("retail_fashion").map((model) => model.label)).toContain("Clothing store");
    expect(operatingModels("wholesale_retail").map((model) => model.label)).toContain("Wholesale business");
    expect(operatingModels("quick_service").map((model) => model.label)).toContain("Fast-food counter");
  });

  it("gives every category an all-in-one operating model", () => {
    for (const card of SIGNUP_BUSINESS_CARDS) {
      expect(card.subTypes.some((model) => model.allInOne)).toBe(true);
    }
  });

  it("previews features that the selected model actually turns on", () => {
    const counter = operatingModels("cafe").find((model) => model.id === "counter_cafe");
    const seated = operatingModels("cafe").find((model) => model.id === "sit_down_cafe");
    const restaurant = operatingModels("restaurant").find((model) => model.id === "restaurant_all");
    const electronics = operatingModels("electronics_wholesale").find((model) => model.id === "electronics_both");
    expect(counter).toBeDefined();
    expect(seated).toBeDefined();
    expect(restaurant).toBeDefined();
    expect(electronics).toBeDefined();
    expect(setupPreview(counter!).included).toEqual(
      expect.arrayContaining(["POS Register", "Kitchen orders", "Menu options"]),
    );
    expect(setupPreview(counter!).included.join(" ")).not.toContain("Table");
    expect(setupPreview(seated!).included).toEqual(expect.arrayContaining(["Table management", "Split bills"]));
    expect(setupPreview(restaurant!).included).toEqual(
      expect.arrayContaining(["Table management", "Kitchen orders", "Delivery orders"]),
    );
    expect(setupPreview(electronics!).included).toEqual(expect.arrayContaining(["IMEI / serial tracking"]));
    expect(setupPreview(restaurant!).note).toContain("separate add-on");
    expect(setupPreview(restaurant!).note).toContain("Paid add-ons");
    expect(setupPreview(restaurant!).included.join(" ")).not.toMatch(/AxizReach|e-Invoicing/);
  });
});

describe("selection rules", () => {
  it("keeps continue disabled until both choices are valid", () => {
    expect(selectionReady(null, null)).toBe(false);
    expect(selectionReady("cafe", null)).toBe(false);
    expect(selectionReady("cafe", "full_service")).toBe(false);
    expect(selectionReady("cafe", "counter_cafe")).toBe(true);
  });

  it("clears an operating model that does not belong to the new category", () => {
    expect(subTypeAfterCategoryChange("restaurant", "counter_cafe")).toBeNull();
    expect(subTypeAfterCategoryChange("cafe", "counter_cafe")).toBe("counter_cafe");
    expect(subTypeAfterCategoryChange("grocery", null)).toBeNull();
  });

  it("refreshes the preview when the operating model changes", () => {
    const shop = operatingModels("grocery").find((model) => model.id === "grocery_mini");
    const fresh = operatingModels("grocery").find((model) => model.id === "grocery_fresh");
    expect(shop).toBeDefined();
    expect(fresh).toBeDefined();
    expect(setupPreview(shop!).included.join(" ")).not.toContain("Weighed");
    expect(setupPreview(fresh!).included).toContain("Weighed items");
    expect(setupPreview(fresh!).note).toContain("scale");
  });
});
