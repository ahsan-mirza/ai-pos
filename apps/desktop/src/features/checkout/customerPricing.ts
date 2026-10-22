import type { CustomerPricing, PriceListEntry } from "@ai-pos/shared-types";
import { call } from "../orders/ordersClient";

const PREFIX = "ai-pos.customer-pricing.";
const memory = new Map<string, CustomerPricing>();

function storage(): Storage | null {
  return typeof localStorage === "undefined" ? null : localStorage;
}

/** The customer's own and group price lists as last fetched; used offline. */
export function cachedPricing(customerId: string | null | undefined): CustomerPricing | null {
  if (!customerId) return null;
  const known = memory.get(customerId);
  if (known) return known;
  const raw = storage()?.getItem(PREFIX + customerId);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as CustomerPricing;
    memory.set(customerId, parsed);
    return parsed;
  } catch {
    return null;
  }
}

export function rememberPricing(pricing: CustomerPricing): void {
  memory.set(pricing.customer_id, pricing);
  try {
    storage()?.setItem(PREFIX + pricing.customer_id, JSON.stringify(pricing));
  } catch {
    // A full store only costs the offline copy; the in-memory one still prices this session.
  }
}

/** Fetches and caches the attached customer's contract prices; resolves null when offline. */
export async function refreshPricing(customerId: string): Promise<CustomerPricing | null> {
  try {
    const pricing = await call<CustomerPricing>("GET", `/api/v1/price-lists/customers/${customerId}`);
    rememberPricing(pricing);
    return pricing;
  } catch {
    return null;
  }
}

/** Entries for one product: its catalogue entries plus the customer's (product-specific or blanket). */
export function entriesFor(
  productId: string,
  catalog: readonly PriceListEntry[] | undefined,
  pricing: CustomerPricing | null,
): PriceListEntry[] {
  const own = (pricing?.entries ?? []).filter((entry) => entry.product_id === productId || entry.product_id === null);
  return [...(catalog ?? []), ...own];
}
