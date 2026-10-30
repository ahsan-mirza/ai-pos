import type { ProductUpsert } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { findVariant, groupHits, inactiveSaleMessage, modelGroup, modelName, variantAxes } from "./variants";

function tee(size: string, color: string, stock = 3, price = 4900): ProductUpsert {
  return {
    id: `tee-${size}-${color}`,
    store_id: "s",
    sku: `TEE-${size}-${color}`,
    barcode: `200${size}${color}`,
    name: `Classic Tee ${size} ${color}`,
    category: "Apparel",
    price_cents: price,
    currency: "AED",
    is_serialized: false,
    stock_quantity: stock,
    product_model_id: "tee",
    variant_attributes: { size, color },
  };
}

const cable: ProductUpsert = {
  id: "cable",
  store_id: "s",
  sku: "CABLE",
  barcode: "1",
  name: "USB-C Cable",
  category: "Accessories",
  price_cents: 1500,
  currency: "AED",
  is_serialized: false,
  stock_quantity: 10,
};

const catalog = [tee("M", "Black"), tee("XL", "Black", 0, 5400), tee("S", "White"), tee("M", "White"), cable];

describe("variant picker", () => {
  it("collapses a model's variants into one card where the first one matched", () => {
    const hits = [{ product: catalog[2]! }, { product: cable }, { product: catalog[0]! }];
    const entries = groupHits(hits, catalog);
    expect(entries.map((entry) => entry.kind)).toEqual(["model", "product"]);
    const model = entries[0]!;
    if (model.kind !== "model") throw new Error("expected a model card");
    expect(model.group.variants).toHaveLength(4);
    expect([model.group.fromCents, model.group.toCents, model.group.stock]).toEqual([4900, 5400, 9]);
  });

  it("orders sizes the way they are worn and finds the cell", () => {
    const group = modelGroup("tee", catalog)!;
    const [size, color] = variantAxes(group.variants);
    expect(size).toEqual({ key: "size", values: ["S", "M", "XL"] });
    expect(color?.values).toEqual(["Black", "White"]);
    expect(findVariant(group.variants, { size: "XL", color: "Black" })?.sku).toBe("TEE-XL-Black");
    expect(findVariant(group.variants, { size: "S", color: "Black" })).toBeUndefined();
    expect(modelName(group.variants[0]!)).toBe("Classic Tee");
  });

  it("drops an inactive variant from the picker but still identifies its barcode", () => {
    const hidden = { ...tee("L", "Navy"), is_active: false as const };
    const products = [...catalog, hidden];
    expect(modelGroup("tee", products)!.variants.map((variant) => variant.id)).not.toContain(hidden.id);
    const scanned = products.find((product) => product.barcode === hidden.barcode);
    expect(scanned?.id).toBe(hidden.id);
    expect(inactiveSaleMessage(scanned!)).toMatch(/inactive/);
    expect(groupHits([{ product: hidden }, { product: catalog[0]! }], products).map((entry) => entry.kind)).toEqual(["model"]);
  });

  it("leaves single variants and plain products as cards", () => {
    const lonely = { ...tee("M", "Red"), product_model_id: "other" };
    expect(groupHits([{ product: lonely }], [lonely]).map((entry) => entry.kind)).toEqual(["product"]);
  });
});
