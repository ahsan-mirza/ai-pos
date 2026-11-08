import type { ProductUpsert } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { cartItemDetail } from "./CartItemCard";

function product(patch: Partial<ProductUpsert>): ProductUpsert {
  return {
    id: "1",
    store_id: "store",
    sku: "SKU-1",
    barcode: "123",
    name: "Item",
    category: "Food",
    price_cents: 100,
    currency: "AED",
    is_serialized: false,
    stock_quantity: 1,
    ...patch,
  };
}

describe("cart item detail", () => {
  it("hides codes on a plain item", () => {
    expect(cartItemDetail(product({ name: "Blueberry muffin", sku: "MUF-1" }))).toBe("");
  });

  it("shows size, colour and sku for a fashion variant", () => {
    expect(cartItemDetail(product({ sku: "TEE-M-BLK", variant_attributes: { size: "M", color: "Black" } }))).toBe(
      "Size M · Colour Black · TEE-M-BLK",
    );
  });

  it("shows the scale code for a weighed item and not its sku", () => {
    expect(cartItemDetail(product({ sku: "APPLE", sold_by_weight: true, plu_code: "4011", barcode: "2004011" }))).toBe("PLU 4011");
  });

  it("shows the sku for a serialized item", () => {
    expect(cartItemDetail(product({ sku: "PHN-1", is_serialized: true, barcode: "imei-box" }))).toBe("PHN-1");
  });
});
