import type { ProductUpsert } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { PriceOptionModal } from "./PriceOptionModal";

const dish = {
  id: "grill",
  name: "Grilled Chicken",
  sku: "GRILL",
  barcode: "200",
  category: "Kitchen",
  price_cents: 1800,
  currency: "USD",
  is_serialized: false,
  stock_quantity: 0,
  store_id: "store",
} as ProductUpsert;

describe("priced option dialog", () => {
  it("starts with no option and stays inside the viewport", () => {
    const html = renderToStaticMarkup(
      <PriceOptionModal
        product={dish}
        options={[
          { id: "breakfast", product_id: "grill", name: "Breakfast", price_cents: 800, sku: null, is_active: true, position: 0 },
          { id: "lunch", product_id: "grill", name: "Lunch", price_cents: 1200, sku: null, is_active: true, position: 1 },
        ]}
        groups={[]}
        currency="USD"
        onClose={() => undefined}
        onConfirm={() => undefined}
      />,
    );
    expect(html).toContain("No option selected");
    expect(html).toContain("Breakfast");
    expect(html).toContain("max-h-[92dvh]");
    expect(html).toContain("max-h-full");
    expect(html).toContain("max-height:100%");
    expect(html).toContain("min-w-0");
    expect(html).toContain("max-w-xl");
    expect(html).toContain("8.00");
    expect(html).toContain("12.00");
    expect(html).toMatch(/disabled[^>]*>[\s\S]*Add to order/);
  });
});
