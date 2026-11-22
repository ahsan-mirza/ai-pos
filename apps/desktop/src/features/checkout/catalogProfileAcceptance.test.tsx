import type { BusinessProfile, ProductUpsert } from "@ai-pos/shared-types";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("framer-motion", async () => {
  const React = await import("react");
  return {
    motion: {
      span: ({ children, className }: { children?: import("react").ReactNode; className?: string }) =>
        React.createElement("span", { className }, children),
    },
    useReducedMotion: () => true,
  };
});
import { RegisterLayoutProvider } from "../../components/RegisterLayout";
import { applyProfile, bindCapabilityTenant } from "../../lib/capabilities";
import { withTerminalAllocation } from "./allocationBalance";
import { catalogueLayoutClass } from "./cataloguePresentation";
import { ProductCard } from "./ProductCard";
import type { Hit } from "./useProductSearch";
import { ModelCard } from "./VariantPicker";
import { modelGroup } from "./variants";

const memory = new Map<string, string>();
const storage = {
  getItem: (key: string) => memory.get(key) ?? null,
  setItem: (key: string, value: string) => {
    memory.set(key, value);
  },
  removeItem: (key: string) => {
    memory.delete(key);
  },
  clear: () => memory.clear(),
  key: () => null,
  get length() {
    return memory.size;
  },
};

vi.stubGlobal("localStorage", storage);
vi.stubGlobal("window", {
  localStorage: storage,
  matchMedia: () => ({ matches: true }),
});

let revision = 1;

function product(patch: Partial<ProductUpsert> = {}): ProductUpsert {
  return {
    id: "item-1",
    store_id: "downtown",
    sku: "SKU-1",
    barcode: "200000000001",
    name: "Acceptance item",
    category: "General",
    price_cents: 1800,
    currency: "USD",
    is_serialized: false,
    stock_quantity: 12,
    ...patch,
  };
}

function hit(item: ProductUpsert): Hit {
  return { product: item, match: "text" };
}

function show(profile: BusinessProfile, item: ProductUpsert, options?: { modifiers?: boolean }) {
  bindCapabilityTenant({ tenantId: "catalog-tile-acceptance", environment: "test" });
  applyProfile({
    tenant_id: "catalog-tile-acceptance",
    environment: "test",
    business_profile: profile,
    capabilities: [],
    entitlement_revision: revision,
  });
  revision += 1;
  return renderToStaticMarkup(
    <RegisterLayoutProvider>
      <ul>
        <ProductCard
          hit={hit(item)}
          preview={null}
          currency="USD"
          disabled={false}
          hasModifiers={options?.modifiers === true}
          onSelect={() => undefined}
          onCheckBranches={() => undefined}
          onInfo={() => undefined}
        />
      </ul>
    </RegisterLayoutProvider>,
  );
}

function badgeBeforePrice(html: string, badge: string): void {
  const badgeAt = html.indexOf(badge);
  const priceAt = html.indexOf('size="card"') === -1 ? html.indexOf("USD") : html.indexOf("USD");
  expect(badgeAt).toBeGreaterThan(-1);
  expect(priceAt).toBeGreaterThan(badgeAt);
}

describe("shared catalogue card by business profile", () => {
  beforeEach(() => {
    memory.clear();
  });

  it("renders a grocery card with image, stock, allocation, and a long price on one row", () => {
    const allocated = withTerminalAllocation(
      product({
        id: "rice",
        name: "Long grain rice with a name that must stay inside two lines",
        category: "Grocery",
        sku: "GROC-RICE",
        price_cents: 12_345_67,
        stock_quantity: 59,
        image_url: "https://acceptance.invalid/rice.png",
        sellable_units: ["PIECE"],
      }),
      new Map([
        ["rice", 40],
        ["other-register-product", 7],
      ]),
      true,
    );
    const html = show("grocery", allocated);
    expect(html).toContain("--pos-product-image-height");
    expect(html).toContain("object-contain");
    expect(html).toContain("absolute end-2 top-2");
    expect(html.indexOf("Details for Long grain rice")).toBeLessThan(html.indexOf("Long grain rice with a name"));
    expect(html).toContain("59 Pieces");
    expect(html).toContain("This register: 40 available");
    expect(html).not.toContain("This register: 7 available");
    badgeBeforePrice(html, "59 Pieces");
    expect(html).toContain("--pos-product-footer-height");
    expect(html).toContain("Branch stock");
    expect(html).toContain("line-clamp-2");
    expect(html).toContain("whitespace-nowrap");
    expect(html).toContain("12,345.67");
  });

  it("keeps a grocery card without a photo inside the same image well", () => {
    const html = show("grocery", product({ name: "Loose onions", image_url: null, thumb_url: null, stock_quantity: 4 }));
    expect(html).toContain("--pos-product-image-height");
    expect(html).not.toContain("<img");
    expect(html).toContain("4 Pieces");
    expect(html).not.toContain("This register:");
  });

  it("represents zero branch stock and an exhausted register allocation without inventing availability", () => {
    const exhausted = withTerminalAllocation(
      product({ id: "milk", name: "Milk", stock_quantity: 0 }),
      new Map([["milk", 0]]),
      true,
    );
    const html = show("grocery", exhausted);
    expect(html).toContain("Out of stock");
    expect(html).toContain("This register: allocation exhausted");
    expect(html).toContain("Find in other branches");
    const missing = show("grocery", product({ name: "Bread", stock_quantity: 3 }));
    expect(missing).toContain("3 Pieces");
    expect(missing).not.toContain("This register:");
  });

  it("shows an electronics card with the serialized marker and this register's allocation", () => {
    const phone = withTerminalAllocation(
      product({
        id: "phone",
        name: "Handheld scanner with a very long wholesale description that stays clamped",
        category: "Electronics",
        sku: "ELEC-SCAN-1",
        model_number: "SCN-9",
        is_serialized: true,
        stock_quantity: 6,
        price_cents: 24900,
      }),
      new Map([["phone", 40]]),
      true,
    );
    const html = show("electronics_wholesale", phone);
    expect(html).toContain("Electronics");
    expect(html).toContain('aria-label="Serialized"');
    expect(html).toContain("6 Pieces");
    expect(html).toContain("This register: 40 available");
    expect(html).toContain("Branch stock");
    expect(html).toContain("Details for Handheld scanner");
  });

  it("shows a fashion stock card and a size card that keep the register allocation accessible", () => {
    const shirt = withTerminalAllocation(
      product({
        id: "shirt-m",
        name: "Linen shirt",
        category: "Fashion",
        sku: "FASH-SHIRT-M",
        stock_quantity: 4,
        product_model_id: "shirt",
        model_name: "Linen shirt",
        variant_attributes: { size: "M", colour: "Sand" },
        price_cents: 8900,
      }),
      new Map([["shirt-m", 40]]),
      true,
    );
    const soldOut = product({
      id: "shirt-s",
      name: "Linen shirt",
      category: "Fashion",
      sku: "FASH-SHIRT-S",
      stock_quantity: 0,
      product_model_id: "shirt",
      model_name: "Linen shirt",
      variant_attributes: { size: "S", colour: "Sand" },
      price_cents: 8900,
    });
    const html = show("retail_fashion", shirt);
    expect(html).toContain("4 Pieces");
    expect(html).toContain("This register: 40 available");
    expect(html).toContain("Branch stock");
    const group = modelGroup("shirt", [shirt, soldOut]);
    expect(group).not.toBeNull();
    const model = renderToStaticMarkup(
      <RegisterLayoutProvider>
        <ul>
          <ModelCard group={group!} currency="USD" disabled={false} onOpen={() => undefined} onInfo={() => undefined} />
        </ul>
      </RegisterLayoutProvider>,
    );
    expect(model).toContain("Choose size &amp; colour");
    expect(model).toContain("This register: 40 available");
    expect(model).toContain("In stock");
    expect(model).toContain("--pos-product-footer-height");
  });

  it("omits the branch-stock footer on restaurant and cafe menu cards", () => {
    const grill = product({
      id: "grill",
      name: "O810 Grill",
      category: "Mains",
      price_cents: 1800,
      stock_quantity: 50,
      image_url: "https://acceptance.invalid/grill.png",
      item_type: "MADE_TO_ORDER",
      is_stock_tracked: false,
    });
    const restaurant = show("restaurant", grill, { modifiers: true });
    expect(restaurant).toContain("O810 Grill");
    expect(restaurant).toContain("+ Modifiers");
    expect(restaurant).toContain("18.00");
    expect(restaurant).toContain("--pos-product-image-height");
    expect(restaurant).toContain("object-contain");
    expect(restaurant).not.toContain("Branch stock");
    expect(restaurant).not.toContain("Find in other branches");
    expect(restaurant).not.toContain("--pos-product-footer-height");
    expect(restaurant).not.toContain("Pieces");
    expect(restaurant).not.toContain("This register:");
    badgeBeforePrice(restaurant, "+ Modifiers");
    const plain = show("cafe", product({ name: "House coffee", image_url: null, thumb_url: null, stock_quantity: 0, is_stock_tracked: false, item_type: "MADE_TO_ORDER" }));
    expect(plain).toContain("House coffee");
    expect(plain).not.toContain("<img");
    expect(plain).not.toContain("Branch stock");
    expect(plain).not.toContain("Out of stock");
    expect(plain).not.toContain("+ Modifiers");
    const priced = show("restaurant", {
      ...grill,
      price_cents: 1500,
      price_options: [
        { id: "breakfast", product_id: "grill", name: "Breakfast", price_cents: 800, is_active: true, position: 0 },
        { id: "dinner", product_id: "grill", name: "Dinner", price_cents: 1500, is_active: true, position: 1 },
      ],
    });
    expect(priced).toContain("From");
    expect(priced).toContain("8.00");
    expect(priced).not.toContain("15.00");
  });

  it("keeps the catalogue grid in rem and the card from stretching to the pane", () => {
    const grid = catalogueLayoutClass("grid");
    expect(grid).toContain("13.125rem");
    expect(grid).toContain("0.875rem");
    expect(grid).toContain("content-start");
    expect(grid).toContain("h-auto");
    expect(grid).not.toMatch(/\d+px/);
    const card = show("grocery", product());
    expect(card).toContain("overflow-hidden");
    expect(card).toContain("min-w-0");
    expect(card).not.toMatch(/h-\[\d+px\]/);
  });
});

describe("laundry order intake", () => {
  it("does not render the shared catalogue card", () => {
    const dir = fileURLToPath(new URL("../laundry", import.meta.url));
    const sources = readdirSync(dir)
      .filter((name) => name.endsWith(".ts") || name.endsWith(".tsx"))
      .map((name) => readFileSync(join(dir, name), "utf8"))
      .join("\n");
    expect(sources).not.toContain("CatalogTile");
    expect(sources).not.toContain("ProductCard");
    expect(sources).toContain("New Order");
  });
});
