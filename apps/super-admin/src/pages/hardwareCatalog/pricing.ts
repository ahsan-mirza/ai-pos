/** AED display helpers. Catalogue money is integer fils, the same unit as the registry API. */

export interface PricedPart {
  quantity: number;
  displayPriceFils: number | null;
  optional: boolean;
}

export function filsFromAed(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

export function aedFromFils(fils: number | null): string {
  if (fils == null) return "";
  return (fils / 100).toFixed(2);
}

/** Required components only. Null when any required price is missing. */
export function componentValueFils(parts: PricedPart[]): number | null {
  let total = 0;
  for (const part of parts) {
    if (part.optional) continue;
    if (part.displayPriceFils == null) return null;
    total += part.quantity * part.displayPriceFils;
  }
  return total;
}

/** Null unless the required components cost more than the configured package price. */
export function savingsFils(parts: PricedPart[], packagePriceFils: number | null): number | null {
  const total = componentValueFils(parts);
  if (total == null || packagePriceFils == null || total <= packagePriceFils) return null;
  return total - packagePriceFils;
}

export function productFieldErrors(input: { name: string; sku: string; displayPrice: string; reason: string }): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!input.name.trim()) errors.name = "Enter a product name.";
  if (!/^[A-Za-z0-9][A-Za-z0-9-]{0,31}$/.test(input.sku.trim())) errors.sku = "Use letters, numbers, and hyphens.";
  if (input.displayPrice.trim() && filsFromAed(input.displayPrice) == null) errors.displayPrice = "Enter a price in AED, such as 1899.00.";
  if (input.reason.trim().length < 3) errors.reason = "Add a short reason.";
  return errors;
}
