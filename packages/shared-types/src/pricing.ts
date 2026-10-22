import { PRICE_TIERS, type PaymentTerms, type PriceTier, type SaleType, type UnitType } from "./enums.js";

/** A quantity break counted in pieces. */
export interface VolumeBreak {
  min_qty: number;
  price_cents: number;
}

/** One product_prices row. RETAIL falls back to products.price_cents when it has no row. */
export interface ProductPrice {
  price_tier: PriceTier;
  price_cents: number;
  min_order_quantity: number;
  volume_discounts: VolumeBreak[];
}

export type PriceSource =
  | "retail"
  | "tier"
  | "volume"
  | "customer_list"
  | "group_list"
  | "store_list"
  | "global_list";

export type PriceListScope = "customer" | "group" | "store" | "global";

/** One price list's item for one product, with its list's scope and validity (what the resolver needs). */
export interface PriceListEntry {
  price_list_id: string;
  scope: PriceListScope;
  scope_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  priority: number;
  is_active: boolean;
  price_cents: number | null;
  discount_bps: number | null;
  min_qty: number;
  volume_breaks: VolumeBreak[];
}

export interface PricingContext {
  customer_id?: string | null;
  group_id?: string | null;
  store_id?: string | null;
  /** ISO time; defaults to now. */
  at?: string | null;
}

export interface ListResolution {
  price_cents: number;
  source: PriceSource;
  tier: PriceTier;
  price_list_id: string | null;
}

/** Row of GET /api/v1/pricing/matrix. */
export interface PricingRow {
  product_id: string;
  sku: string;
  name: string;
  brand: string | null;
  category: string;
  category_id: string | null;
  is_serialized: boolean;
  retail_price_cents: number;
  min_order_quantity: number;
  sellable_units: UnitType[];
  prices: ProductPrice[];
}

export interface PricingMatrix {
  currency: string;
  rows: PricingRow[];
  brands: string[];
}

export interface TierPriceWrite {
  price_tier: PriceTier;
  /** null removes the tier's own price so it falls back to the next lower tier. */
  price_cents: number | null;
  min_order_quantity: number;
  volume_discounts: VolumeBreak[];
}

/** PUT /api/v1/pricing/products/{id}. Omitted fields are left unchanged. */
export interface ProductPricingWrite {
  retail_price_cents?: number;
  min_order_quantity?: number;
  sellable_units?: UnitType[];
  tiers?: TierPriceWrite[];
}

export type BulkPriceMode = "set" | "percent_of_retail" | "adjust_percent";

export interface BulkPriceUpdate {
  product_ids?: string[] | null;
  category_id?: string | null;
  brand?: string | null;
  price_tier: PriceTier;
  mode: BulkPriceMode;
  price_cents?: number | null;
  /** Basis points: 8500 = 85% of retail; -500 = 5% below the current tier price. */
  percent_bps?: number | null;
  min_order_quantity?: number | null;
  volume_discounts?: VolumeBreak[] | null;
}

export interface BulkPriceResult {
  updated: number;
  skipped: number;
}

export interface PriceResolution {
  price_cents: number;
  tier: PriceTier;
  source: PriceSource;
  min_order_quantity: number;
  /** Pieces still needed to reach the requested tier's minimum order quantity; 0 when met. */
  moq_shortfall: number;
}

export const DEFAULT_WHOLESALE_TIER: PriceTier = "TIER_1";

export const PRICE_TIER_LABELS: Record<PriceTier, string> = {
  RETAIL: "Retail",
  TIER_1: "Wholesale T1",
  TIER_2: "Wholesale T2",
  DISTRIBUTOR: "Distributor",
};

export const UNIT_LABELS: Record<UnitType, { short: string; long: string }> = {
  PIECE: { short: "Pcs", long: "Pieces" },
  BOX_10: { short: "Box", long: "Box of 10" },
  CARTON_100: { short: "Carton", long: "Carton of 100" },
};

export const PAYMENT_TERMS_LABELS: Record<PaymentTerms, string> = {
  DUE_ON_RECEIPT: "Due on receipt",
  NET_15: "Net 15",
  NET_30: "Net 30",
  NET_60: "Net 60",
};

export function effectiveTier(saleType: SaleType, customerTier: PriceTier | null | undefined): PriceTier {
  if (saleType !== "WHOLESALE") return "RETAIL";
  return customerTier ?? DEFAULT_WHOLESALE_TIER;
}

/**
 * Unit price per piece for `pieces` at `tier`. Mirrors apps/api/app/services/pricing.py; both are checked
 * against fixtures/pricing-cases.json. A tier without its own row, or whose minimum order quantity is not
 * met, falls back to the nearest lower tier.
 */
export function resolveUnitPrice(
  retailCents: number,
  prices: readonly ProductPrice[] | undefined,
  tier: PriceTier,
  pieces: number,
): PriceResolution {
  const rows = new Map((prices ?? []).map((row) => [row.price_tier, row]));
  const wanted = Math.max(0, PRICE_TIERS.indexOf(tier));
  let shortfall = 0;
  for (let index = wanted; index >= 0; index -= 1) {
    const name = PRICE_TIERS[index] as PriceTier;
    const row = rows.get(name);
    if (row === undefined && name !== "RETAIL") continue;
    const moq = row?.min_order_quantity ?? 1;
    if (name !== "RETAIL" && pieces < moq) {
      if (index === wanted) shortfall = moq - pieces;
      continue;
    }
    const base = name === "RETAIL" ? retailCents : (row?.price_cents ?? retailCents);
    let best = base;
    for (const item of row?.volume_discounts ?? []) {
      if (pieces >= item.min_qty && item.price_cents < best) best = item.price_cents;
    }
    const source: PriceSource = best < base ? "volume" : name === "RETAIL" ? "retail" : "tier";
    return { price_cents: best, tier: name, source, min_order_quantity: moq, moq_shortfall: shortfall };
  }
  return { price_cents: retailCents, tier: "RETAIL", source: "retail", min_order_quantity: 1, moq_shortfall: 0 };
}

const SCOPE_RANK: Record<PriceListScope, number> = { customer: 0, group: 1, store: 2, global: 3 };

/** Whether a price-list entry is in scope and in date. Mirrors entry_applies in pricing.py. */
export function entryApplies(entry: PriceListEntry, context: PricingContext): boolean {
  if (!entry.is_active) return false;
  if (entry.scope !== "global") {
    const wanted = entry.scope === "customer" ? context.customer_id : entry.scope === "group" ? context.group_id : context.store_id;
    if (!entry.scope_id || !wanted || entry.scope_id !== wanted) return false;
  }
  const moment = Date.parse(context.at ?? new Date().toISOString());
  if (entry.valid_from && moment < Date.parse(entry.valid_from)) return false;
  return !(entry.valid_to && moment >= Date.parse(entry.valid_to));
}

/**
 * The lowest valid price: price lists (customer, group, store, business-wide) against the tier and volume price.
 * A discount entry takes its basis points off the tier price; equal prices go to the more specific scope, then
 * the higher priority. Mirrors resolve_with_lists in pricing.py; both are checked against price-list-cases.json.
 */
export function resolveWithLists(
  retailCents: number,
  prices: readonly ProductPrice[] | undefined,
  tier: PriceTier,
  pieces: number,
  entries: readonly PriceListEntry[] | undefined,
  context: PricingContext = {},
): ListResolution {
  const base = resolveUnitPrice(retailCents, prices, tier, pieces);
  let best: [number, number, number] = [base.price_cents, 4, 0];
  let source: PriceSource = base.source;
  let listId: string | null = null;
  for (const entry of entries ?? []) {
    if (!entryApplies(entry, context) || pieces < (entry.min_qty || 1)) continue;
    let price =
      entry.price_cents !== null
        ? entry.price_cents
        : Math.floor((base.price_cents * (10_000 - (entry.discount_bps ?? 0)) + 5_000) / 10_000);
    for (const item of entry.volume_breaks ?? []) {
      if (pieces >= item.min_qty && item.price_cents < price) price = item.price_cents;
    }
    const rank: [number, number, number] = [price, SCOPE_RANK[entry.scope], -(entry.priority || 0)];
    if (rank[0] < best[0] || (rank[0] === best[0] && (rank[1] < best[1] || (rank[1] === best[1] && rank[2] < best[2])))) {
      best = rank;
      source = `${entry.scope}_list`;
      listId = entry.price_list_id;
    }
  }
  return { price_cents: best[0], source, tier: base.tier, price_list_id: listId };
}

/** The next volume break above `pieces` at the resolved tier, for "add N more for X each" hints. */
export function nextVolumeBreak(
  prices: readonly ProductPrice[] | undefined,
  tier: PriceTier,
  pieces: number,
): VolumeBreak | null {
  const row = (prices ?? []).find((item) => item.price_tier === tier);
  const ahead = (row?.volume_discounts ?? []).filter((item) => item.min_qty > pieces);
  ahead.sort((left, right) => left.min_qty - right.min_qty);
  return ahead[0] ?? null;
}
