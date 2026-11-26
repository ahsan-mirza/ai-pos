import { formatMoney, fromPriceCents, type MenuPriceOption, type PriceDraft } from "@ai-pos/shared-types";

export type PortionMode = "single" | "portions";

export function blankPortions(): PriceDraft[] {
  return [
    { name: "", price: "", active: true },
    { name: "", price: "", active: true },
  ];
}

export function portionsFromOptions(options: readonly MenuPriceOption[]): PriceDraft[] {
  return [...options]
    .sort((left, right) => left.position - right.position || left.name.localeCompare(right.name))
    .map((option) => ({
      id: option.id,
      name: option.name,
      price: (option.price_cents / 100).toFixed(2),
      active: option.is_active,
    }));
}

/** Seed the current product price into the first blank portion so a mode switch does not drop it. */
export function portionsSeededFromPrice(rows: readonly PriceDraft[], price: string): PriceDraft[] {
  const started = rows.some((row) => row.name.trim() !== "" || row.price.trim() !== "");
  if (started) return [...rows];
  return [
    { name: "", price, active: true },
    { name: "", price: "", active: true },
  ];
}

export function movePortion<T>(rows: readonly T[], index: number, direction: -1 | 1): T[] {
  const target = index + direction;
  if (index < 0 || target < 0 || index >= rows.length || target >= rows.length) return [...rows];
  const copy = [...rows];
  const [moved] = copy.splice(index, 1);
  if (moved === undefined) return [...rows];
  copy.splice(target, 0, moved);
  return copy;
}

export function catalogPriceLabel(product: {
  price_cents: number;
  currency: string;
  price_options?: readonly MenuPriceOption[];
}): string {
  const from = fromPriceCents(product.price_options);
  if (from === null) return formatMoney(product.price_cents, product.currency);
  return `From ${formatMoney(from, product.currency)}`;
}

export function isMultiplePortionProduct(product: { price_options?: readonly MenuPriceOption[] }): boolean {
  return fromPriceCents(product.price_options) !== null;
}
