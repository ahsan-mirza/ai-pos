import type { ProductUpsert } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { productFitsRegister } from "./industry";

function product(patch: Partial<ProductUpsert>): ProductUpsert {
  return {
    id: "p",
    store_id: "s",
    sku: "SKU",
    barcode: "000",
    name: "Dish",
    category: "Mains",
    price_cents: 100,
    currency: "AED",
    is_serialized: false,
    stock_quantity: 1,
    ...patch,
  };
}

describe("productFitsRegister", () => {
  it("hides phones, cables, and repair labour from a restaurant", () => {
    expect(productFitsRegister(product({ name: "Pixel 9", category: "Phones", is_serialized: true }), "restaurant")).toBe(false);
    expect(productFitsRegister(product({ name: "USB-C Cable", category: "Accessories", sku: "CABLE" }), "cafe")).toBe(false);
    expect(productFitsRegister(product({ name: "Repair labour", category: "Services", is_service: true }), "quick_service")).toBe(false);
    expect(productFitsRegister(product({ name: "Latitude 5520", category: "General", model_number: "DELL-7441" }), "restaurant")).toBe(false);
    expect(productFitsRegister(product({ name: "Classic beef burger", category: "Burgers" }), "restaurant")).toBe(true);
  });

  it("hides menu dishes from an electronics register", () => {
    expect(productFitsRegister(product({ name: "Classic beef burger", category: "Burgers" }), "electronics_wholesale")).toBe(false);
    expect(productFitsRegister(product({ name: "USB-C Cable", category: "Accessories" }), "electronics_wholesale")).toBe(true);
  });
});
