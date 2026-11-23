import type { MenuPriceOption, ProductUpsert } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { claimSubmit, parseSellQuantity, releaseSubmit, sellLineTotalCents } from "./QuantityField";
import { QuantityModal } from "./QuantityModal";

const water = {
  id: "water",
  name: "Mineral Water",
  sku: "WATER",
  barcode: "100",
  category: "Drinks",
  price_cents: 200,
  currency: "AED",
  is_serialized: false,
  stock_quantity: 0,
  store_id: "store",
} as ProductUpsert;

const portions: MenuPriceOption[] = [
  { id: "small", product_id: "daal", name: "Small Plate", price_cents: 300, sku: null, is_active: true, position: 0 },
  { id: "medium", product_id: "daal", name: "Medium Plate", price_cents: 500, sku: null, is_active: true, position: 1 },
  { id: "full", product_id: "daal", name: "Full Plate", price_cents: 900, sku: null, is_active: true, position: 2 },
];

const daal = { ...water, id: "daal", name: "Daal Channa", sku: "DAAL", price_cents: 300 } as ProductUpsert;

describe("sell quantity", () => {
  it("rejects empty, zero, negative, and text", () => {
    expect(parseSellQuantity("")).toBeNull();
    expect(parseSellQuantity("0")).toBeNull();
    expect(parseSellQuantity("-1")).toBeNull();
    expect(parseSellQuantity("1.5")).toBeNull();
    expect(parseSellQuantity("no")).toBeNull();
    expect(parseSellQuantity("2")).toBe(2);
  });

  it("ignores a second submit while the first confirmation is still claimed", () => {
    const guard = { current: false };
    expect(claimSubmit(guard)).toBe(true);
    expect(claimSubmit(guard)).toBe(false);
    releaseSubmit(guard);
    expect(claimSubmit(guard)).toBe(true);
  });

  it("multiplies the selected portion in minor units", () => {
    expect(sellLineTotalCents(300, "2")).toBe(600);
    expect(sellLineTotalCents(500, "2")).toBe(1000);
    expect(sellLineTotalCents(900, "3")).toBe(2700);
    expect(sellLineTotalCents(200, "0")).toBeNull();
  });
});

describe("quantity and portion modal", () => {
  it("hides portions for a single price and offers the stepper", () => {
    const html = renderToStaticMarkup(
      <QuantityModal product={water} currency="AED" onClose={() => undefined} onConfirm={() => true} />,
    );
    expect(html).toContain("How many are you selling?");
    expect(html).not.toContain("Portion size");
    expect(html).toContain("Decrease quantity");
    expect(html).toContain("Increase quantity");
    expect(html).toContain("Add 1 —");
  });

  it("shows portions with none selected and keeps add disabled", () => {
    const html = renderToStaticMarkup(
      <QuantityModal product={daal} options={portions} currency="AED" onClose={() => undefined} onConfirm={() => true} />,
    );
    expect(html).toContain("Choose portion and quantity.");
    expect(html).toContain("Small Plate");
    expect(html).toContain("Medium Plate");
    expect(html).toContain("Full Plate");
    expect(html).toContain("No portion selected");
    expect(html).toContain("choice-control");
    expect(html).not.toContain("ring-2");
    expect(html).toContain("aria-checked=\"false\"");
    expect(html).toMatch(/disabled[^>]*>[\s\S]*Add to sale/);
  });

  it("preselects a portion only when an existing line is edited", () => {
    const html = renderToStaticMarkup(
      <QuantityModal
        product={daal}
        options={portions}
        currency="AED"
        initialQuantity={2}
        initialOptionId="medium"
        editing
        onClose={() => undefined}
        onConfirm={() => true}
      />,
    );
    expect(html).toContain("aria-checked=\"true\"");
    expect(html).toContain("Update 2 × Medium Plate");
    expect(html).toContain("value=\"2\"");
  });
});
