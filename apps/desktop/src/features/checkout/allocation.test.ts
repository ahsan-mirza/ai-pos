import { describe, expect, it } from "vitest";
import type { ProductUpsert } from "@ai-pos/shared-types";
import { withTerminalAllocation } from "./allocationBalance";
import { applyCart, emptyCart } from "./cart";

const product = {
  id: "p1",
  sku: "RICE",
  barcode: "1",
  name: "Rice",
  category: "Grocery",
  price_cents: 100,
  currency: "USD",
  is_serialized: false,
  stock_quantity: 100,
  sold_by_weight: false,
} as ProductUpsert;

describe("offline allocation", () => {
  it("does not treat branch stock as the terminal balance", () => {
    const blocked = applyCart(emptyCart, {
      type: "add_product",
      product: { ...product, allocation_remaining: null } as ProductUpsert,
      quantity: 1,
    });
    expect(blocked.error).toContain("ALLOCATION NOT CONFIGURED");

    const over = applyCart(emptyCart, {
      type: "add_product",
      product: { ...product, allocation_remaining: 3 } as ProductUpsert,
      quantity: 5,
    });
    expect(over.error).toContain("Available offline allocation: 3");
    expect(over.error).toContain("Requested: 5");

    const allowed = applyCart(emptyCart, {
      type: "add_product",
      product: { ...product, allocation_remaining: 3 } as ProductUpsert,
      quantity: 3,
    });
    expect(allowed.error).toBeNull();
  });

  it("stamps the terminal remainder and does not keep branch stock as the offline balance", () => {
    const balances = new Map([["p1", 4]]);
    const stamped = withTerminalAllocation(product, balances, true);
    expect(stamped.allocation_remaining).toBe(4);
    expect(stamped.stock_quantity).toBe(100);
    const missing = withTerminalAllocation({ ...product, id: "other" }, balances, true);
    expect(missing.allocation_remaining).toBeNull();
    const online = withTerminalAllocation(product, balances, false);
    expect("allocation_remaining" in online).toBe(false);
  });
});
