import {
  DEFAULT_MODULE_SETTINGS,
  DEFAULT_TAX_POLICY,
  buildEmbeddedBarcode,
  parseEmbeddedBarcode,
  weighedLineCents,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { applyCart, cartTotals, emptyCart, lineCharge } from "./cart";

const apples: ProductUpsert = {
  id: "apples",
  store_id: "store",
  sku: "PRD-APPLE-RED",
  barcode: "2000000000001",
  name: "Red apples",
  category: "Produce",
  price_cents: 1299,
  currency: "USD",
  is_serialized: false,
  stock_quantity: 5_000,
  sold_by_weight: true,
  plu_code: "4016",
  tare_grams: 15,
};

const labels = DEFAULT_MODULE_SETTINGS.weighed_items.embedded_barcodes;

describe("weighed goods", () => {
  it("prices grams at the per-kg price, rounding half up like the API", () => {
    expect(weighedLineCents(1234, 1299)).toBe(1603);
    expect(weighedLineCents(500, 1001)).toBe(501);
  });

  it("adds each weighing as its own line and refuses piece counting", () => {
    let result = applyCart(emptyCart, { type: "add_weighed", product: apples, grams: 1234 });
    expect(result.error).toBeNull();
    result = applyCart(result.state, { type: "add_weighed", product: apples, grams: 500 });
    expect(result.state.lines.map((line) => line.quantity)).toEqual([1234, 500]);
    expect(applyCart(result.state, { type: "add_product", product: apples }).error).toMatch(/Weigh/);
    expect(applyCart(result.state, { type: "set_packs", lineId: result.state.lines[0]!.lineId, packs: 2 }).error).toMatch(/Weigh/);
    expect(applyCart(result.state, { type: "add_weighed", product: apples, grams: 4_000 }).error).toMatch(/Only 5.000 kg/);

    const policy = { ...DEFAULT_TAX_POLICY, standard_rate_bps: 0 };
    expect(lineCharge(result.state.lines[0]!, policy).line_total_cents).toBe(1603);
    expect(cartTotals(result.state.lines, policy).total).toBe(1603 + 650);
    const vat = lineCharge(result.state.lines[0]!, { ...DEFAULT_TAX_POLICY, standard_rate_bps: 500 });
    expect(vat.line_total_cents - vat.tax_cents).toBe(1603);
  });

  it("reads scale labels with a valid check digit only", () => {
    const label = buildEmbeddedBarcode("21", "4016", 1234);
    expect(label).toHaveLength(13);
    expect(parseEmbeddedBarcode(label, labels)).toEqual({ plu: "4016", grams: 1234, priceCents: null });
    const broken = `${label.slice(0, 12)}${(Number(label[12]) + 1) % 10}`;
    expect(parseEmbeddedBarcode(broken, labels)).toBeNull();
    expect(parseEmbeddedBarcode(buildEmbeddedBarcode("31", "4016", 1234), labels)).toBeNull();
    expect(parseEmbeddedBarcode(label, { ...labels, mode: "price" })).toEqual({ plu: "4016", grams: null, priceCents: 1234 });
  });
});
