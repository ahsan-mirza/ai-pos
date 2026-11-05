import { describe, expect, it } from "vitest";
import type { ProductUpsert } from "@ai-pos/shared-types";
import { BUNDLED_DEMO_IDS, mergeCatalog, withoutBundledDemo } from "./catalog";

function product(id: string, name: string): ProductUpsert {
  return { id, sku: id, name, price_cents: 100, currency: "PKR", stock_quantity: 1 } as ProductUpsert;
}

describe("checkout catalogue loading", () => {
  it("drops the bundled sample rows", () => {
    const demo = product([...BUNDLED_DEMO_IDS][0]!, "USB-C Cable");
    const real = product("real-1", "Basmati Rice 5kg");
    expect(withoutBundledDemo([demo, real]).map((row) => row.name)).toEqual(["Basmati Rice 5kg"]);
  });

  it("keeps the current catalogue when a refresh fails with nothing new", () => {
    const current = [product("real-1", "Basmati Rice 5kg")];
    const next = mergeCatalog(current, {
      products: [],
      source: "cache",
      message: "Unable to refresh the catalogue. Showing the last synchronized products.",
    });
    expect(next.products).toEqual(current);
    expect(next.message).toContain("last synchronized");
  });

  it("accepts a successful empty catalogue", () => {
    const next = mergeCatalog([product("real-1", "Basmati Rice 5kg")], {
      products: [],
      source: "api",
      message: null,
    });
    expect(next.products).toEqual([]);
    expect(next.source).toBe("api");
  });
});
