export type TradeInGrade = "A" | "B" | "C" | "D";
export type TradeInPayout = "CASH" | "STORE_CREDIT" | "SALE_CREDIT";

export const TRADE_IN_GRADE_LABELS: Record<TradeInGrade, string> = {
  A: "A · Like new",
  B: "B · Light wear",
  C: "C · Heavy wear",
  D: "D · Faulty",
};

export interface TradeInChecklist {
  powers_on: boolean;
  screen_ok: boolean;
  body_ok: boolean;
  /** iCloud / Google account and screen lock removed. */
  account_removed: boolean;
  battery_pct: number | null;
}

export interface TradeInCheckResult {
  ok: boolean;
  message: string;
  sold_here_at: string | null;
  sold_as: string | null;
  warranty_status: string | null;
}

export interface TradeIn {
  id: string;
  number: string;
  store_id: string;
  store_code: string;
  product_id: string;
  product_name: string;
  resale_product_id: string;
  resale_sku: string;
  identifier_kind: "imei" | "serial";
  identifier_tail: string;
  grade: TradeInGrade;
  checklist: TradeInChecklist;
  notes: string;
  seller_name: string;
  seller_phone: string;
  seller_id_last4: string;
  customer_id: string | null;
  offer_cents: number;
  resale_price_cents: number;
  currency: string;
  payout: TradeInPayout;
  status: "ACCEPTED" | "APPLIED" | "CANCELLED";
  sale_id: string | null;
  store_credit_code: string | null;
  cashier_name: string | null;
  created_at: string;
}

export interface TradeInList {
  items: TradeIn[];
  bought_cents: number;
  count: number;
  awaiting_sale_cents: number;
}
