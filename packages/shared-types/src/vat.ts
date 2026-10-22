import type { Emirate } from "./store";

export interface VatEmirateRow {
  emirate: Emirate | null;
  label: string;
  amount_cents: number;
  vat_cents: number;
  adjustment_cents: number;
}

export interface VatBox {
  key: string;
  label: string;
  amount_cents: number;
  vat_cents: number;
}

/** GET /reports/vat: VAT201 working figures for a period. */
export interface VatReport {
  period_from: string;
  period_to: string;
  store_id: string | null;
  currency: string;
  trn: string | null;
  legal_name: string | null;
  vat_registered: boolean;
  emirates: VatEmirateRow[];
  boxes: VatBox[];
  output_vat_cents: number;
  input_vat_cents: number;
  net_vat_cents: number;
  input_vat_estimated: boolean;
  invoices: number;
  full_invoices: number;
  simplified_invoices: number;
  credit_notes: number;
}
