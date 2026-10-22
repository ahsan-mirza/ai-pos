import type { PaymentMethod, SaleType } from "./enums.js";
import type { Sale } from "./sale.js";
import type { SaleItemUpsert } from "./sale-item.js";

/** POST /api/v1/quotes. Serialized lines carry one IMEI each, or a quantity with IMEIs assigned at conversion. */
export interface QuoteUpsert {
  id: string;
  store_id: string;
  cashier_id: string;
  currency: string;
  sale_type: SaleType;
  customer_id: string | null;
  valid_days: number;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  items: SaleItemUpsert[];
  quote_kind?: QuoteKind;
  /** First deposit, taken when a layaway is created. */
  deposit?: QuotePaymentInput | null;
}

/** QUOTE: a proforma offer. LAYAWAY: goods held against deposits until paid in full. */
export type QuoteKind = "QUOTE" | "LAYAWAY";

export interface QuotePaymentInput {
  id: string;
  amount_cents: number;
  method: "cash" | "card" | "transfer";
  reference?: string;
  shift_id?: string | null;
}

export interface QuotePayment {
  id: string;
  amount_cents: number;
  method: string;
  reference: string;
  status: "ACTIVE" | "APPLIED" | "REFUND_DUE";
  received_by_name: string | null;
  received_at: string;
}

export interface Quote extends Sale {
  number: string;
  cashier_name: string | null;
  quote_kind?: QuoteKind;
  deposits_cents?: number;
  refund_due_cents?: number;
  payments?: QuotePayment[];
}

export interface QuoteStats {
  open_count: number;
  open_value_cents: number;
  converted_count: number;
  converted_value_cents: number;
  expired_count: number;
  cancelled_count: number;
  conversion_rate_bps: number;
  expiring_soon_count: number;
}

export interface QuoteList {
  currency: string;
  stats: QuoteStats;
  /** One page of the quotes matching the status filter. */
  quotes: Quote[];
  /** Every quote matching the status filter (also sent as X-Total-Count). */
  total: number;
}

export interface TenderInput {
  method: PaymentMethod;
  amount_cents: number;
  reference?: string;
}

export interface QuoteConvert {
  sale_id?: string;
  payment_method: PaymentMethod;
  tenders?: TenderInput[];
  credit_override?: { approved_by_id: string; note: string } | null;
}
