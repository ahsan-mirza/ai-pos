export type WarrantyScope = "DEFAULT" | "CATEGORY" | "PRODUCT";
export type WarrantyCoverage = "IN_WARRANTY" | "EXPIRED" | "NOT_FOUND" | "VOID";

export interface WarrantyPolicy {
  id: string;
  name: string;
  scope: WarrantyScope;
  category_id: string | null;
  product_id: string | null;
  months: number;
  terms: string;
  is_active: boolean;
}

export interface WarrantyPolicyWrite {
  name: string;
  scope: WarrantyScope;
  category_id?: string | null;
  product_id?: string | null;
  months: number;
  terms?: string;
  is_active?: boolean;
}

/** Extended cover, sold at the register through its own service product. */
export interface WarrantyPlan {
  id: string;
  name: string;
  extra_months: number;
  product_id: string;
  sku: string;
  price_cents: number;
  terms: string;
  is_active: boolean;
}

export interface WarrantyRegistration {
  id: string;
  sale_id: string;
  invoice: string;
  product_name: string;
  serial: string | null;
  customer_id: string | null;
  customer_name: string | null;
  plan_name: string | null;
  starts_at: string;
  expires_at: string;
  status: "ACTIVE" | "CLAIMED" | "VOID";
  coverage: WarrantyCoverage;
  claims: number;
}

export interface WarrantyRegistrationList {
  active_count: number;
  expiring_count: number;
  extended_count: number;
  registrations: WarrantyRegistration[];
}
