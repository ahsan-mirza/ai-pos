export type MarginScope = "GLOBAL" | "CATEGORY" | "PRODUCT";

export interface MarginPolicy {
  id: string;
  scope: MarginScope;
  category_id: string | null;
  category_name: string | null;
  product_id: string | null;
  product_name: string | null;
  /** Minimum margin over cost in basis points; 2000 = 20%. */
  min_margin_bps: number;
  is_active: boolean;
}

export interface MarginPolicyWrite {
  scope: MarginScope;
  category_id?: string | null;
  product_id?: string | null;
  min_margin_bps: number;
  is_active?: boolean;
}

export interface MarginException {
  sale_id: string;
  invoice: string;
  store_code: string;
  sold_at: string;
  product_name: string;
  quantity: number;
  unit_price_cents: number;
  floor_cents: number;
  shortfall_cents: number;
  cashier_name: string | null;
  approved_by_name: string | null;
  currency: string;
}

export interface MarginExceptionList {
  total_shortfall_cents: number;
  exceptions: MarginException[];
}
