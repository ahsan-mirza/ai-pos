import seed from "@ai-pos/catalog/seed.json";
import type { ProductPrice, ProductUpsert, StoreUpsert, UnitType } from "@ai-pos/shared-types";
import { listProducts } from "../../lib/api";
import { inTauri, refreshProducts } from "../../lib/tauri";
import { registerCapabilities } from "../../lib/capabilities";
import { productFitsRegister } from "../../lib/industry";
import { GIFT_CARD_SKU } from "./cart";
import { activeStore, syncBusinessCurrency } from "./currency";

/** Store identity only; its currency comes from `activeStore()` / `useBusinessCurrency()`. */
export const store: StoreUpsert = activeStore();
export const taxRateBps: number = seed.tax_rate_bps;

const seedPricing = new Map(seed.wholesale.pricing.map((spec) => [spec.sku, spec]));

/** Offline fallback: seed opening stock only belongs to the seed products' home branch. */
export const seedProducts: ProductUpsert[] = seed.products.map((product) => {
  const pricing = seedPricing.get(product.sku);
  return {
    ...product,
    store_id: store.id,
    stock_quantity: product.store_id === store.id ? product.stock_quantity : 0,
    min_order_quantity: pricing?.min_order_quantity ?? 1,
    sellable_units: (pricing?.sellable_units ?? ["PIECE"]) as UnitType[],
    prices: (pricing?.tiers ?? []) as ProductPrice[],
    origin: "seed" as const,
  };
});

export interface Catalog {
  products: ProductUpsert[];
  source: "api" | "cache" | "seed";
  message: string | null;
}

async function fetchCatalog(): Promise<Catalog> {
  if (inTauri()) {
    const snapshot = await refreshProducts();
    return { products: snapshot.products, source: snapshot.source, message: snapshot.message };
  }
  try {
    return { products: await listProducts(), source: "api", message: null };
  } catch (error) {
    const message = error instanceof Error ? error.message : "API unavailable.";
    return { products: seedProducts, source: "seed", message };
  }
}

export async function loadCatalog(): Promise<Catalog> {
  const [catalog, currency] = await Promise.all([fetchCatalog(), syncBusinessCurrency()]);
  // Ingredients are stocked for recipes only; the register never sells them. Gift cards are sold from their own
  // button, which loads the card product with the business's amount rules.
  const profile = registerCapabilities().profile;
  const sellable = catalog.products.filter(
    (product) => !product.is_ingredient && product.sku !== GIFT_CARD_SKU && productFitsRegister(product, profile),
  );
  return { ...catalog, products: sellable.map((product) => ({ ...product, currency })) };
}
