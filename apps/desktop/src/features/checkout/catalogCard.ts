import { PROFILE_PRESETS, type BusinessProfile } from "@ai-pos/shared-types";

const UNIT_NAMES: Record<string, string> = {
  PIECE: "Pieces",
  BOX_10: "Box of 10",
  CARTON_100: "Carton of 100",
};

/** Shared catalogue-tile measurements. Every card reserves these slots so a row stays aligned. */
export const catalogCardClass = {
  name: "line-clamp-2 min-h-10 min-w-0 flex-1 text-left text-sm font-semibold leading-5",
  footer: "mt-2 flex min-h-10 min-w-0 flex-nowrap items-center justify-between gap-2",
} as const;

export function productCode(sku?: string | null, modelNumber?: string | null): string {
  return [sku, modelNumber]
    .map((part) => part?.trim() ?? "")
    .filter(Boolean)
    .join(" · ");
}

/** Menu cards lead with the dish and its price. Stock cards lead with the quantity this branch can sell. */
export type CardKind = "menu" | "stock";

export function cardKind(profile: BusinessProfile): CardKind {
  return PROFILE_PRESETS[profile].group === "food_beverage" ? "menu" : "stock";
}

export type StockTone = "in" | "low" | "out" | "untracked";

/** Selling state from the branch figures. Low stock uses the reorder point the inventory service stored. */
export function stockTone(input: {
  tracked: boolean;
  available: number;
  onHand?: number;
  reorder?: number | null;
}): StockTone {
  if (!input.tracked) return "untracked";
  if (input.available <= 0) return "out";
  const onHand = input.onHand ?? input.available;
  if (input.reorder != null && input.reorder > 0 && onHand <= input.reorder) return "low";
  return "in";
}

export function stockUnit(product: { sold_by_weight?: boolean; sellable_units?: readonly string[] | null }): string {
  if (product.sold_by_weight) return "";
  const code = product.sellable_units?.[0] ?? "PIECE";
  return UNIT_NAMES[code] ?? "Units";
}

/** Same short line the till already uses for specifications: up to three values. */
export function productDetail(specs?: Record<string, string>): string {
  return Object.values(specs ?? {})
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 3)
    .join(" · ");
}
