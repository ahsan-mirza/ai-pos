export type StockCountStatus = "OPEN" | "SUBMITTED" | "POSTED" | "CANCELLED";

export const STOCK_COUNT_STATUS_LABELS: Record<StockCountStatus, string> = {
  OPEN: "Counting",
  SUBMITTED: "Awaiting review",
  POSTED: "Posted",
  CANCELLED: "Cancelled",
};

export interface StockCountLine {
  product_id: string;
  sku: string;
  name: string;
  barcode: string;
  is_serialized: boolean;
  counted_qty: number | null;
  /** Null for counters while a blind count is open. */
  expected_qty: number | null;
  variance: number | null;
  variance_value_cents: number | null;
  scanned_tails: string[];
  missing_serials: string[] | null;
  unexpected_serials: string[] | null;
  counted_by_name: string | null;
  counted_at: string | null;
}

export interface StockCountSummary {
  id: string;
  number: string;
  store_name: string;
  category_name: string | null;
  status: StockCountStatus;
  blind: boolean;
  created_by_name: string | null;
  created_at: string;
  closed_at: string | null;
  lines_total: number;
  lines_counted: number;
  net_variance: number | null;
  variance_value_cents: number | null;
}

export interface StockCount extends StockCountSummary {
  store_id: string;
  category_id: string | null;
  note: string;
  can_review: boolean;
  submitted_at: string | null;
  lines: StockCountLine[];
}

export interface StockCountEntry {
  product_id: string;
  counted_qty?: number;
  serials?: { kind: "imei" | "serial"; value: string }[];
}
