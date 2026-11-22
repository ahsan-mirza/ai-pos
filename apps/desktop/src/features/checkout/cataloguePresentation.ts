import { formatWeight, type ProductUpsert } from "@ai-pos/shared-types";
import type { CatalogueView } from "./cataloguePreference";
import { stockTone, stockUnit } from "./catalogCard";

const cards = "grid min-w-0 content-start items-stretch [&>li]:h-auto [&>li]:min-w-0 [&>li]:w-full";

/** Columns follow the catalogue width. A card starts at 13.125rem and does not inherit the pane height. */
export function catalogueLayoutClass(view: CatalogueView): string {
  if (view === "list") return "flex min-w-0 flex-col gap-2";
  if (view === "compact") {
    return `${cards} gap-[0.875rem] [grid-template-columns:repeat(auto-fill,minmax(min(100%,11.25rem),1fr))]`;
  }
  return `${cards} gap-[0.875rem] [grid-template-columns:repeat(auto-fill,minmax(min(100%,13.125rem),1fr))]`;
}

/** SKU, barcode, and category, using only values the product already has. */
export function catalogueIdentity(product: { sku?: string | null; barcode?: string | null; category?: string | null }): string {
  return [product.sku, product.barcode, product.category]
    .map((part) => part?.trim() ?? "")
    .filter(Boolean)
    .join(" · ");
}

export function catalogueTracked(product: ProductUpsert): boolean {
  return product.is_stock_tracked !== false && !product.is_service && !product.has_recipe && product.item_type !== "MADE_TO_ORDER";
}

/** The same stock line the grid card shows. Menu cards do not show a shelf count. */
export function catalogueStockLabel(product: ProductUpsert, menu: boolean): string | null {
  if (menu) return null;
  const tone = stockTone({ tracked: catalogueTracked(product), available: product.stock_quantity });
  if (tone === "untracked") return "Not tracked";
  if (tone === "out") return "Out of stock";
  if (product.sold_by_weight) return formatWeight(product.stock_quantity);
  const unit = stockUnit(product);
  return unit ? `${product.stock_quantity} ${unit}` : String(product.stock_quantity);
}

/** A list row hides Add when the cart would refuse the product for being out of stock. */
export function blocksCatalogueAdd(product: ProductUpsert): boolean {
  return catalogueTracked(product) && product.stock_quantity <= 0;
}
