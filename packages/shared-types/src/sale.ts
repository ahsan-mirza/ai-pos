import type { PaymentMethod, PaymentStatus, QuoteStatus, SaleStatus, SaleType } from "./enums.js";
import type { SaleItem, SaleItemUpsert } from "./sale-item.js";

export interface ChequeDetails {
  cheque_number: string;
  bank: string;
  /** YYYY-MM-DD; a future date makes it a post-dated cheque. */
  cheque_date: string;
}

/** amount_cents is always in the business currency; foreign tenders also record what was handed over. */
export interface SaleTender {
  method: PaymentMethod;
  amount_cents: number;
  reference: string;
  cheque?: ChequeDetails | null;
  currency?: string | null;
  foreign_amount_cents?: number | null;
  /** Business-currency change handed back on a foreign cash tender. */
  change_cents?: number | null;
  rate_micros?: number | null;
  payment_intent_id?: string | null;
  /** A card taken on a standalone machine where the store's terminals are integrated: who allowed it. */
  manual_override?: { approved_by_id: string; note: string } | null;
  /** Voucher spent by a store_credit tender, e.g. SC-AB12-CD34-EF56. */
  store_credit_code?: string | null;
  /** Gift card spent by a gift_card tender, e.g. GC-AB12-CD34-EF56. */
  gift_card_code?: string | null;
  /** The trade-in a trade_in tender spends. */
  trade_in_id?: string | null;
}

export interface StoreCreditUse {
  sale_id: string;
  invoice_number: string | null;
  amount_cents: number;
  used_at: string;
}

export interface StoreCreditVoucher {
  id: string;
  code: string;
  store_id: string;
  store_name: string;
  currency: string;
  initial_cents: number;
  balance_cents: number;
  issued_at: string;
  /** Null for vouchers issued by a trade-in. */
  return_id: string | null;
  uses: StoreCreditUse[];
  /** VOUCHER: refund or trade-in credit. GIFT_CARD: sold or issued as a gift. */
  kind?: "VOUCHER" | "GIFT_CARD";
  issued_sale_id?: string | null;
  customer_id?: string | null;
  customer_name?: string | null;
  expires_at?: string | null;
  voided_at?: string | null;
  note?: string;
  /** Spendable now: not voided, not expired, money left. */
  usable?: boolean;
}

export interface StoreCreditList {
  items: StoreCreditVoucher[];
  outstanding_cents: number;
  open_count: number;
}

export interface Sale {
  id: string;
  store_id: string;
  cashier_id: string;
  status: SaleStatus;
  currency: string;
  payment_method: PaymentMethod;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  client_sale_id: string;
  invoice_number?: string | null;
  items: SaleItem[];
  sale_type: SaleType;
  customer_id: string | null;
  customer_name: string | null;
  is_quote_proforma: boolean;
  quote_expiry_date: string | null;
  quote_status: QuoteStatus | null;
  converted_sale_id: string | null;
  payment_status: PaymentStatus;
  amount_paid_cents: number;
  due_balance_cents: number;
  due_date: string | null;
  tenders: SaleTender[];
  created_at: string;
  updated_at: string;
}

/** Sync payload. Older registers omit sale_type/tenders; the API reads that as one fully paid tender. */
export interface SaleUpsert {
  id: string;
  store_id: string;
  cashier_id: string;
  currency: string;
  payment_method: PaymentMethod;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  client_sale_id: string;
  items: SaleItemUpsert[];
  sale_type?: SaleType;
  customer_id?: string | null;
  tenders?: SaleTender[];
  credit_override?: { approved_by_id: string; note: string } | null;
  sold_at?: string;
  invoice_number?: string | null;
  shift_id?: string | null;
  loyalty_points_redeemed?: number | null;
  coupon_code?: string | null;
  /** The restaurant tab this sale pays, and which of its lines (all unpaid lines when empty). */
  order_id?: string | null;
  order_item_ids?: string[];
  /** Service charge inside total_cents; its VAT is inside tax_cents. */
  service_charge_cents?: number;
  service_charge_tax_cents?: number;
  /** Tip for staff on top of total_cents; tenders cover total + tip. */
  tip_cents?: number;
  tip_user_id?: string | null;
  /** The stylist who served the customer when it is not the cashier; commissions credit them. */
  sales_associate_id?: string | null;
}
