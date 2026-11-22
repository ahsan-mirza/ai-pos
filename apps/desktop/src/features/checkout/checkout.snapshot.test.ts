import { describe, expect, it } from "vitest";
import type { CartLine } from "./cart";
import { saleItems } from "./queue";

describe("checkout financial snapshot", () => {
  it("stores the unit price, tax, and rate used for the line", () => {
    const line = {
      product: { id: "p", tax_category: "STANDARD", price_includes_tax: false },
      quantity: 1,
      unitPriceCents: 1500,
      unitType: "PIECE",
      serialValue: null,
      serialKind: null,
      listPriceCents: 1500,
      override: null,
    } as CartLine;
    const [item] = saleItems([line], { enforced: true, prices_include_vat: false, standard_rate_bps: 500 });
    expect(item).toBeDefined();
    if (item === undefined) return;
    expect(item.unit_price_cents).toBe(1500);
    expect(item.tax_rate_bps).toBe(500);
    expect(item.tax_cents).toBe(75);
    expect(item.line_total_cents).toBe(1575);
  });
});
