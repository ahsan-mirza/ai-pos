import { specSchemaFor } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

function keys(profile: string, category: string, sub = ""): string[] {
  return specSchemaFor(category, sub, { profile }).fields.map((field) => field.key);
}

describe("specSchemaFor", () => {
  it("gives a restaurant burger food details and never battery capacity", () => {
    const burger = keys("restaurant", "Burgers");
    expect(burger).toContain("patty_type");
    expect(burger).toContain("spice_level");
    expect(burger).not.toContain("battery");
    expect(keys("quick_service", "Burgers & Wraps")).toEqual(burger);
    expect(keys("restaurant", "Phones")).toEqual([]);
    expect(keys("restaurant", "Smartphones")).not.toContain("battery");
  });

  it("keeps battery on electronics phones and does not borrow restaurant fields", () => {
    expect(keys("electronics_wholesale", "Smartphones")).toContain("battery");
    expect(keys("electronics_wholesale", "Burgers")).toEqual([]);
    expect(keys("electronics_wholesale", "Dresses")).not.toContain("fabric");
  });

  it("keeps cafe, grocery, and fashion on their own templates", () => {
    expect(keys("cafe", "Hot coffee")).toContain("milk_type");
    expect(keys("cafe", "Burgers")).toEqual([]);
    expect(keys("cafe", "Smartphones")).not.toContain("battery");
    expect(keys("grocery", "Dairy")).toContain("net_weight");
    expect(keys("grocery", "Dresses")).not.toContain("fabric");
    expect(keys("grocery", "Phones")).not.toContain("battery");
    expect(keys("retail_fashion", "Dresses")).toContain("fabric");
    expect(keys("retail_fashion", "Burgers")).toEqual([]);
    expect(keys("retail_fashion", "Smartphones")).not.toContain("battery");
  });

  it("returns an empty template when the business type has no match", () => {
    expect(keys("wholesale_retail", "Burgers")).toEqual([]);
    expect(keys("wholesale_retail", "Smartphones")).toEqual([]);
    expect(specSchemaFor("Burgers", "", {}).id).toBe("OTHER");
    expect(specSchemaFor("", "", { profile: "restaurant" }).fields).toEqual([]);
  });
});
