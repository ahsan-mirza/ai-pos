/** Practice mode inside a store: the "First win" checklist and Go live. Mirrors app/schemas/onboarding.py. */

export type ChecklistKey = "test_sale" | "real_product" | "import_stock" | "till" | "cashier" | "go_live";

export interface ChecklistItem {
  key: ChecklistKey;
  label: string;
  hint: string;
  done: boolean;
  /** Portal path, or "#go-live" for the Go live modal. */
  href: string;
}

export interface OnboardingChecklist {
  practice_mode: boolean;
  live_at: string | null;
  /** Typed back to confirm Go live. */
  store_name: string;
  items: ChecklistItem[];
}

export interface GoLiveRequest {
  confirm: string;
}

export interface GoLiveResult {
  live_at: string;
  sales_removed: number;
  sample_products_removed: number;
  sample_customers_removed: number;
}
