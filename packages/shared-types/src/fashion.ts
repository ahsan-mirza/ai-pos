/** Variant matrices, consignment stock and barcode labels (Retail & Fashion). */

export interface MatrixAxis {
  key: string;
  values: string[];
}

export interface MatrixWrite {
  axes: MatrixAxis[];
  price_cents: number;
  /** Price for combinations containing a value, e.g. { XXL: 5900 }; the highest match wins. */
  price_by_value?: Record<string, number>;
  sku_prefix?: string | null;
  tax_category?: "STANDARD" | "ZERO" | "EXEMPT";
}

export interface MatrixCell {
  attributes: Record<string, string>;
  product_id: string;
  sku: string;
  barcode: string;
  name: string;
  price_cents: number;
  on_hand: number;
  sold_90d: number;
  by_store: Record<string, number>;
}

export interface VariantMatrix {
  model_id: string;
  model_name: string;
  axes: MatrixAxis[];
  cells: MatrixCell[];
  on_hand: number;
  sold_90d: number;
  created: number;
  skipped: number;
}

export interface ConsignmentItem {
  batch_item_id: string;
  batch_id: string;
  batch_number: string;
  store_code: string;
  product_id: string;
  sku: string;
  name: string;
  received: number;
  on_hand: number;
  sold: number;
  settled: number;
  unsettled: number;
  unit_cost_cents: number;
  unsettled_cents: number;
}

export interface ConsignmentSupplier {
  supplier_id: string;
  supplier_name: string;
  batches: number;
  units_on_hand: number;
  value_on_hand_cents: number;
  units_sold: number;
  unsettled_units: number;
  unsettled_cents: number;
  settled_cents: number;
  items: ConsignmentItem[];
}

export interface ConsignmentOverview {
  currency: string;
  units_on_hand: number;
  value_on_hand_cents: number;
  unsettled_cents: number;
  suppliers: ConsignmentSupplier[];
}

export interface ConsignmentSettlement {
  id: string;
  number: string;
  supplier_id: string;
  supplier_name: string;
  store_code: string;
  period_end: string;
  units: number;
  total_cents: number;
  bill_id: string;
  bill_total_cents: number;
  bill_status: string;
  created_at: string;
}

export type LabelLayout = "a4_3x8" | "roll_50x30" | "roll_50x25" | "roll_38x25";

export const LABEL_LAYOUT_LABELS: Record<LabelLayout, string> = {
  a4_3x8: "A4 sheet · 24 labels (70 × 37 mm)",
  roll_50x30: "Label roll · 50 × 30 mm",
  roll_50x25: "Standard POS · 50 × 25 mm",
  roll_38x25: "Compact jewelry · 38 × 25 mm",
};

/** Letter sizes in wear order, then numeric sizes, then the rest A-Z. Mirrors variant_matrix_service._value_order. */
const SIZE_ORDER = ["XXXS", "XXS", "XS", "S", "M", "L", "XL", "XXL", "2XL", "XXXL", "3XL", "4XL", "5XL"];

export function compareVariantValues(a: string, b: string): number {
  const rank = (value: string): [number, number, string] => {
    const index = SIZE_ORDER.indexOf(value.toUpperCase());
    if (index >= 0) return [0, index, ""];
    const number = /^\d+(\.\d+)?/.exec(value);
    if (number) return [1, Number(number[0]), value.toLowerCase()];
    return [2, 0, value.toLowerCase()];
  };
  const [ga, na, sa] = rank(a);
  const [gb, nb, sb] = rank(b);
  return ga - gb || na - nb || sa.localeCompare(sb);
}
