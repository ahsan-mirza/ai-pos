import type { EmbeddedBarcodeSettings } from "./settings.js";

/** Weighed goods count grams; price_cents on the product is per kilogram. Mirrors app/services/weighed.py. */
export function weighedLineCents(grams: number, pricePerKgCents: number): number {
  // Round half up on the exact product so the register and the API agree to the cent.
  return Math.floor((grams * pricePerKgCents + 500) / 1000);
}

export function formatWeight(grams: number): string {
  if (Math.abs(grams) < 1000) return `${grams} g`;
  return `${(grams / 1000).toFixed(3)} kg`;
}

/** Days from today (local date) until a YYYY-MM-DD expiry; negative once expired. */
export function daysUntil(isoDate: string, now: Date = new Date()): number {
  const [year, month, day] = isoDate.split("-").map(Number);
  const target = Date.UTC(year!, month! - 1, day!);
  const today = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((target - today) / 86_400_000);
}

export interface EmbeddedBarcode {
  plu: string;
  /** Present for weight labels. */
  grams: number | null;
  /** Present for price labels: the line price in cents. */
  priceCents: number | null;
}

function ean13CheckDigit(first12: string): number {
  let sum = 0;
  for (let index = 0; index < 12; index += 1) {
    sum += Number(first12[index]) * (index % 2 === 0 ? 1 : 3);
  }
  return (10 - (sum % 10)) % 10;
}

/**
 * A scale label: 2-digit prefix, PLU, value, EAN-13 check digit. With plu_length 5 the value has 5 digits
 * (grams up to 99.999 kg, or a price up to 999.99). Returns null for anything that is not such a label.
 */
export function parseEmbeddedBarcode(code: string, settings: EmbeddedBarcodeSettings): EmbeddedBarcode | null {
  const value = code.trim();
  if (!/^\d{13}$/.test(value)) return null;
  if (!settings.prefixes.includes(value.slice(0, 2))) return null;
  if (ean13CheckDigit(value.slice(0, 12)) !== Number(value[12])) return null;
  const pluEnd = 2 + settings.plu_length;
  const plu = value.slice(2, pluEnd).replace(/^0+(?=\d)/, "");
  const amount = Number(value.slice(pluEnd, 12));
  if (!Number.isFinite(amount) || amount <= 0) return null;
  return settings.mode === "weight" ? { plu, grams: amount, priceCents: null } : { plu, grams: null, priceCents: amount };
}

/** Builds a valid label for tests and label printing. */
export function buildEmbeddedBarcode(prefix: string, plu: string, amount: number, pluLength = 5): string {
  const valueLength = 10 - pluLength;
  const body = `${prefix}${plu.padStart(pluLength, "0")}${String(amount).padStart(valueLength, "0")}`;
  return `${body}${ean13CheckDigit(body)}`;
}
