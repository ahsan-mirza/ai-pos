import type { ProductUpsert } from "@ai-pos/shared-types";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CatalogueViewToggle } from "./CatalogueViewToggle";
import { CompactProductCard, ProductListRow } from "./CatalogueRows";
import type { Hit } from "./useProductSearch";

function product(stock: number, extra: Partial<ProductUpsert> = {}): ProductUpsert {
  return {
    id: "p1",
    store_id: "store",
    sku: "MED-001",
    barcode: "6280000000011",
    name: "Acceptance Medicine A",
    category: "OTC",
    price_cents: 1500,
    currency: "AED",
    is_serialized: false,
    stock_quantity: stock,
    ...extra,
  };
}

function hit(stock: number, extra: Partial<ProductUpsert> = {}): Hit {
  return { product: product(stock, extra), match: "text" };
}

describe("catalogue view controls", () => {
  it("highlights only the selected view", () => {
    const toggle = renderToStaticMarkup(<CatalogueViewToggle value="list" onChange={() => undefined} />);
    expect(toggle).toContain('aria-label="Product catalogue view"');
    expect(toggle).toContain('aria-label="Grid view"');
    expect(toggle).toContain('aria-label="List view"');
    expect(toggle).toContain('aria-label="Compact view"');
    expect(toggle.match(/aria-checked="true"/g)).toHaveLength(1);
    expect(toggle).toContain('aria-label="List view"');
    expect(toggle).not.toContain("<input");
  });

  it("keeps an out-of-stock list row from adding and still offers details", () => {
    const unavailable = renderToStaticMarkup(
      <ProductListRow hit={hit(0)} currency="AED" amount={1500} menu={false} disabled={false} onSelect={() => undefined} onInfo={() => undefined} />,
    );
    expect(unavailable).toContain("Acceptance Medicine A");
    expect(unavailable).toContain("MED-001 · 6280000000011 · OTC");
    expect(unavailable).toContain("Out of stock");
    expect(unavailable).toContain("Details for Acceptance Medicine A");
    expect(unavailable).not.toContain("Add Acceptance Medicine A");
  });

  it("adds an in-stock product from the list and the compact card", () => {
    const coffee = hit(5, { name: "Coffee", sku: "CAFE-001", barcode: "", category: "Drinks" });
    const row = renderToStaticMarkup(
      <ProductListRow hit={coffee} currency="AED" amount={1200} menu={false} disabled={false} onSelect={() => undefined} onInfo={() => undefined} />,
    );
    expect(row).toContain("Add Coffee");
    expect(row).toContain("CAFE-001 · Drinks");
    expect(row).not.toContain("CAFE-001 ·  ·");
    const card = renderToStaticMarkup(
      <CompactProductCard hit={coffee} currency="AED" amount={1200} menu={false} disabled={false} onSelect={() => undefined} onInfo={() => undefined} />,
    );
    expect(card).toContain("Coffee");
    expect(card).toContain("Details for Coffee");
    expect(card).toContain("5 Pieces");
  });
});
