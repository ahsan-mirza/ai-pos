import { describe, expect, it } from "vitest";
import { purchaseOrderLines, receiptLines, transferLines } from "./documentLines";

const two = [
  { key: "a", productId: "oats", quantity: "2", cost: "1.25" },
  { key: "b", productId: "rice", quantity: "4", cost: "0" },
];

describe("multi-line inventory documents", () => {
  it("sends every purchase line in one payload", () => {
    const result = purchaseOrderLines(two);
    expect(result).toEqual({
      lines: [
        { product_id: "oats", quantity_ordered: 2, unit_cost_cents: 125 },
        { product_id: "rice", quantity_ordered: 4, unit_cost_cents: 0 },
      ],
    });
  });

  it("rejects a repeated product and a blank line", () => {
    expect(purchaseOrderLines([two[0], { ...two[0], key: "c" }])).toEqual({
      error: "Each product can appear only once on this document.",
    });
    expect(purchaseOrderLines([{ ...two[0], productId: "" }])).toEqual({
      error: "Choose a product on every line.",
    });
  });

  it("keeps a transfer inside two different stores", () => {
    expect(transferLines("store-a", "store-a", two)).toEqual({
      error: "Source and destination must be different stores.",
    });
    const result = transferLines("store-a", "store-b", two);
    expect(result).toEqual({
      lines: [
        { product_id: "oats", quantity: 2 },
        { product_id: "rice", quantity: 4 },
      ],
    });
  });

  it("receives several outstanding lines and refuses an over-receipt", () => {
    const sources = [
      { id: "l1", name: "Oats", quantity_ordered: 5, quantity_received: 1 },
      { id: "l2", name: "Rice", quantity_ordered: 2, quantity_received: 0, lot_controlled: true },
    ];
    expect(
      receiptLines(sources, {
        l1: { quantity: "2", lot: "", expiry: "" },
        l2: { quantity: "1", lot: "LOT-1", expiry: "2027-01-01" },
      }, true),
    ).toEqual({
      lines: [
        { purchase_order_line_id: "l1", quantity: 2, manufacturer_lot: null, expiry_date: null },
        { purchase_order_line_id: "l2", quantity: 1, manufacturer_lot: "LOT-1", expiry_date: "2027-01-01" },
      ],
    });
    expect(receiptLines(sources, { l1: { quantity: "9", lot: "", expiry: "" }, l2: { quantity: "0", lot: "", expiry: "" } }, false)).toEqual({
      error: "Oats has only 4 left to receive.",
    });
  });
});
