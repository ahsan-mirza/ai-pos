import type { SerialKind, SerialStatus } from "./enums.js";

export interface SerialNumber {
  id: string;
  product_id: string;
  store_id: string;
  kind: SerialKind;
  value: string;
  status: SerialStatus;
  created_at: string;
  updated_at: string;
}

/** A row from `GET /api/v1/serials/search`, the one serial lookup used across the app. */
export interface SerialSearchRow {
  id: string;
  product_id: string;
  product_name: string | null;
  sku: string | null;
  store_id: string;
  store_code: string;
  kind: SerialKind;
  /** The full IMEI/serial for registers and stock managers; "•••• 1234" for everyone else. */
  value: string;
  last4: string;
  status: SerialStatus | "registered" | "received";
  batch_number: string | null;
  /** Only for portal users who manage inventory or read reports. */
  purchase_cost_cents: number | null;
  created_at: string;
  updated_at: string;
}

export interface SerialSearchResult {
  /** exact: a full identifier; suffix: its last characters; all: no query; none: the query cannot be searched. */
  match: "exact" | "suffix" | "all" | "none";
  rows: SerialSearchRow[];
  hint: string | null;
}

export interface SerialNumberUpsert {
  id: string;
  product_id: string;
  store_id: string;
  kind: SerialKind;
  value: string;
  status: SerialStatus;
}
