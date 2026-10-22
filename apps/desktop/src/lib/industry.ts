import type { BusinessProfile, ProductUpsert } from "@ai-pos/shared-types";

const FNB = new Set<BusinessProfile>(["restaurant", "cafe", "quick_service"]);

/** Retail sample departments that must not appear on a food register. */
const ELECTRONICS_CATEGORIES = new Set(["phones", "accessories", "computers", "laptops", "audio", "services", "repair"]);
const FASHION_CATEGORIES = new Set(["tops", "bottoms", "footwear", "modest wear"]);
const FOOD_CATEGORIES = new Set(["starters", "mains", "burgers", "sides", "drinks", "beverages", "desserts", "combos"]);
const RETAIL_SAMPLE = /pixel|usb-c|repair labour|repair labor|\bimei\b/i;

export function isFnBProfile(profile: BusinessProfile): boolean {
  return FNB.has(profile);
}

export function isElectronicsProfile(profile: BusinessProfile): boolean {
  return profile === "electronics_wholesale";
}

export function isRetailProfile(profile: BusinessProfile): boolean {
  return !isFnBProfile(profile);
}

function categoryOf(product: ProductUpsert): string {
  return (product.category ?? "").trim().toLowerCase();
}

/** Keep only products this business type sells. A restaurant catalog drops phones, cables, and repair labour. */
export function productFitsRegister(product: ProductUpsert, profile: BusinessProfile): boolean {
  const category = categoryOf(product);
  if (isFnBProfile(profile)) {
    if (product.is_serialized || product.is_service) return false;
    if (ELECTRONICS_CATEGORIES.has(category) || FASHION_CATEGORIES.has(category)) return false;
    if (RETAIL_SAMPLE.test(product.name) || RETAIL_SAMPLE.test(product.sku)) return false;
    // A model number or a computer-style name is retail stock filed under a generic category.
    if (!FOOD_CATEGORIES.has(category) && !product.has_recipe && (product.model_number || /latitude|macbook|iphone|galaxy|pixel|charger|usb-c/i.test(product.name))) {
      return false;
    }
    return true;
  }
  if (isElectronicsProfile(profile) || profile === "retail_fashion") {
    if (FOOD_CATEGORIES.has(category)) return false;
  }
  if (profile === "retail_fashion" && product.is_serialized) return false;
  return true;
}

/** Touch-menu chips for food, and the electronics quick filters. Value is the catalog category. */
export function categoryChips(profile: BusinessProfile): { value: string; label: string }[] {
  if (isFnBProfile(profile)) {
    return [
      { value: "Mains", label: "Main Course" },
      { value: "Burgers", label: "Burgers" },
      { value: "Drinks", label: "Beverages" },
      { value: "Desserts", label: "Desserts" },
      { value: "Combos", label: "Combos" },
    ];
  }
  if (isElectronicsProfile(profile)) {
    return [
      { value: "Accessories", label: "Accessories" },
      { value: "Phones", label: "Phones" },
      { value: "Services", label: "Services" },
      { value: "Laptops", label: "Laptops" },
    ];
  }
  return [];
}

export function searchPlaceholder(profile: BusinessProfile): string {
  if (isFnBProfile(profile)) return "Search the menu…";
  if (isElectronicsProfile(profile)) return "Scan barcode or search name, model, SKU, or IMEI...";
  if (profile === "retail_fashion") return "Scan barcode or search name, SKU, size, or colour…";
  return "Scan barcode or search name or SKU…";
}

export function searchLabel(profile: BusinessProfile): string {
  if (isFnBProfile(profile)) return "Search the menu";
  if (isElectronicsProfile(profile)) return "Search product, model, barcode, or IMEI";
  return "Search product, barcode, or SKU";
}
