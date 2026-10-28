/** Guided trial inside a store. Mirrors app/schemas/onboarding.py. */

export type ChecklistKey = "explore" | "configure" | "catalogue" | "practice" | "team" | "activate";

export interface ChecklistItem {
  key: ChecklistKey;
  label: string;
  hint: string;
  done: boolean;
  /** Portal path, or "#go-live" for the Go live modal. */
  href: string;
  action: string;
  optional: boolean;
  skipped: boolean;
  blocked: string | null;
  secondary_href: string | null;
  secondary_label: string | null;
  /** True when an optional action inside the step can be skipped without counting as done. */
  skippable: boolean;
}

export type GoLiveMode = "keep" | "fresh";
export type OpeningStockChoice = "keep" | "reset";

export interface OnboardingChecklist {
  version: number;
  practice_mode: boolean;
  live_at: string | null;
  /** Typed back to confirm Go live. */
  store_name: string;
  /** Units Keep opening stock would carry, with practice sales put back. */
  opening_stock_units: number;
  /** trial, pending_review, active, grace, restricted, or unbilled. */
  subscription_state: string;
  next_key: ChecklistKey | null;
  items: ChecklistItem[];
}

export interface OnboardingSkip {
  key: string;
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
