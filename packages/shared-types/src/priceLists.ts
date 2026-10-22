import type { PaymentTerms, PriceTier } from "./enums.js";
import type { PriceListEntry, PriceListScope, VolumeBreak } from "./pricing.js";
import type { TaxTreatment } from "./tax.js";

export const PRICE_LIST_SCOPE_LABELS: Record<PriceListScope, string> = {
  customer: "One customer",
  group: "Customer group",
  store: "One branch",
  global: "Whole business",
};

export interface CustomerGroupWrite {
  name: string;
  default_tier: PriceTier | null;
  /** Blanket discount off the tier price, in basis points. */
  default_discount_bps: number;
  payment_terms: PaymentTerms | null;
  is_active: boolean;
}

export interface CustomerGroup extends CustomerGroupWrite {
  id: string;
  members: number;
  price_lists: number;
}

export interface PriceListWrite {
  name: string;
  scope: PriceListScope;
  scope_id: string | null;
  valid_from: string | null;
  valid_to: string | null;
  priority: number;
  is_active: boolean;
}

export type PriceListStatus = "active" | "scheduled" | "expired" | "off";

export interface PriceListRow extends PriceListWrite {
  id: string;
  currency: string;
  scope_name: string | null;
  items: number;
  status: PriceListStatus;
}

export interface PriceListItemWrite {
  product_id: string;
  price_cents: number | null;
  discount_bps: number | null;
  min_qty: number;
  volume_breaks: VolumeBreak[];
}

export interface PriceListItem extends PriceListItemWrite {
  sku: string;
  name: string;
  retail_price_cents: number;
}

export interface PriceList extends PriceListRow {
  lines: PriceListItem[];
}

export interface CsvImportResult {
  imported: number;
  skipped: string[];
}

export type PriceChangeStatus = "SCHEDULED" | "APPLIED" | "CANCELLED";

export interface PriceChangeLineWrite {
  product_id: string;
  retail_price_cents: number | null;
  tier_prices: Partial<Record<PriceTier, number>>;
}

export interface PriceChangeWrite {
  name: string;
  run_at: string;
  note: string;
  lines: PriceChangeLineWrite[];
}

export interface PriceChangeLine {
  product_id: string;
  sku: string;
  name: string;
  current_retail_cents: number;
  retail_price_cents: number | null;
  current_tier_prices: Record<string, number>;
  tier_prices: Record<string, number>;
  previous_retail_cents: number | null;
  previous_tier_prices: Record<string, number> | null;
}

export interface PriceChange {
  id: string;
  name: string;
  run_at: string;
  status: PriceChangeStatus;
  note: string;
  created_by_name: string | null;
  applied_at: string | null;
  lines: PriceChangeLine[];
}

/** One entry of a customer's cached pricing; product_id null applies to every product (a group discount). */
export interface CustomerPriceEntry extends PriceListEntry {
  product_id: string | null;
}

/** GET /api/v1/price-lists/customers/{id}: what a register caches when the customer is attached. */
export interface CustomerPricing {
  customer_id: string;
  group_id: string | null;
  tier: PriceTier;
  tax_treatment: TaxTreatment;
  tax_certificate_expiry: string | null;
  entries: CustomerPriceEntry[];
  fetched_at: string;
}
