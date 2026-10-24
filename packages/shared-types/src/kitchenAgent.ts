/** Cards from the kitchen brief. Figures come from stock, recipes, and batches. */

export type KitchenKind =
  | "order"
  | "use_first"
  | "push_today"
  | "write_off"
  | "cannot_make"
  | "prep"
  | "transfer"
  | "waste"
  | "margin"
  | "overstock";

export type KitchenSeverity = "high" | "medium" | "low";

export type KitchenActionName = "draft_purchase" | "draft_transfer" | "write_off";

export interface KitchenCard {
  id: string;
  kind: KitchenKind;
  severity: KitchenSeverity;
  title: string;
  body: string;
  product_id?: string | null;
  batch_item_id?: string | null;
  store_id?: string | null;
  source_store_id?: string | null;
  quantity?: number | null;
  supplier_name?: string | null;
  action?: KitchenActionName | null;
  href?: string | null;
}

export interface KitchenBrief {
  generated_at: string;
  store_id?: string | null;
  cards: KitchenCard[];
}

export interface KitchenActionIn {
  action: KitchenActionName;
  product_id?: string | null;
  store_id?: string | null;
  source_store_id?: string | null;
  quantity?: number | null;
  batch_item_id?: string | null;
  supplier_name?: string | null;
}

export interface KitchenActionOut {
  action: KitchenActionName;
  reference: string;
  href: string;
}
