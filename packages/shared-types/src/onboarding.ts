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

export type GoLiveMode = "keep" | "fresh";
export type OpeningStockChoice = "keep" | "reset";

export interface OnboardingChecklist {
  practice_mode: boolean;
  live_at: string | null;
  /** Typed back to confirm Go live. */
  store_name: string;
  /** Units Keep opening stock would carry, with practice sales put back. */
  opening_stock_units: number;
  items: ChecklistItem[];
}

export interface GoLiveRequest {
  confirm: string;
  mode: GoLiveMode;
  /** Required when mode is keep. Fresh always resets stock. */
  opening_stock?: OpeningStockChoice | null;
  /** The owner has seen that practice tax stamps will be removed. */
  tax_acknowledged: boolean;
}

export interface GoLiveResult {
  live_at: string;
  mode: GoLiveMode;
  opening_stock: OpeningStockChoice;
  sales_removed: number;
  sample_products_removed: number;
  sample_customers_removed: number;
}
