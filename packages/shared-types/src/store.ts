/** UAE emirate codes used on tax invoices and the VAT return's per-emirate boxes. */
export type Emirate = "AUH" | "DXB" | "SHJ" | "AJM" | "UAQ" | "RAK" | "FUJ";

export const EMIRATE_LABELS: Record<Emirate, string> = {
  AUH: "Abu Dhabi",
  DXB: "Dubai",
  SHJ: "Sharjah",
  AJM: "Ajman",
  UAQ: "Umm Al Quwain",
  RAK: "Ras Al Khaimah",
  FUJ: "Fujairah",
};

/** A retail branch or a central distribution warehouse. */
export interface Store {
  id: string;
  code: string;
  name: string;
  currency: string;
  address?: string | null;
  phone?: string | null;
  country?: string | null;
  city?: string | null;
  emirate?: Emirate | null;
  is_warehouse?: boolean;
  is_active?: boolean;
  created_at: string;
  updated_at: string;
}

export interface StoreUpsert {
  id: string;
  code: string;
  name: string;
  currency: string;
  address?: string | null;
  phone?: string | null;
  emirate?: Emirate | null;
  is_warehouse?: boolean;
  is_active?: boolean;
}

export interface StoreUpdate {
  name?: string;
  address?: string | null;
  phone?: string | null;
  country?: string | null;
  city?: string | null;
  emirate?: Emirate | null;
  confirm_country_change?: boolean;
  is_warehouse?: boolean;
  is_active?: boolean;
}
