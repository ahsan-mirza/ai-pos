import type { SaleStatus, SerialKind, SerialStatus } from "./enums.js";
import type { PurchaseOrderStatus } from "./inventory.js";

export interface ProductSaleRow {
  sale_id: string;
  sale_item_id: string;
  invoice: string;
  sold_at: string;
  store_id: string;
  store_code: string;
  store_name: string;
  cashier_name: string | null;
  status: SaleStatus;
  currency: string;
  quantity: number;
  unit_price_cents: number;
  tax_cents: number;
  line_total_cents: number;
  cost_cents: number | null;
  cost_estimated: boolean;
  gross_profit_cents: number | null;
}

/** Summary figures cover every sale in `currency` (the business currency), not just the returned rows. */
export interface ProductSalesHistory {
  currency: string;
  units_sold: number;
  revenue_cents: number;
  average_selling_price_cents: number | null;
  sale_count: number;
  rows: ProductSaleRow[];
}

export interface ProductPurchaseRow {
  purchase_order_id: string;
  po_number: string;
  po_status: PurchaseOrderStatus;
  goods_receipt_id: string | null;
  grn_number: string | null;
  supplier_name: string;
  store_id: string;
  store_code: string;
  ordered_at: string | null;
  received_at: string | null;
  unit_cost_cents: number;
  quantity_ordered: number;
  quantity_received: number;
  total_cost_cents: number;
}

export interface ProductPurchaseHistory {
  latest_unit_cost_cents: number | null;
  average_unit_cost_cents: number | null;
  units_received: number;
  total_spend_cents: number;
  rows: ProductPurchaseRow[];
}

export interface ProductSerialRow {
  serial_number_id: string;
  kind: SerialKind;
  last4: string;
  status: SerialStatus;
  store_id: string;
  store_code: string;
  store_name: string;
  sold_at: string | null;
  sale_invoice: string | null;
  updated_at: string;
}

export interface CostLayerRow {
  batch_item_id: string;
  batch_id: string;
  batch_number: string;
  goods_receipt_id: string | null;
  receipt_date: string;
  original_quantity: number;
  remaining_quantity: number;
  unit_cost_cents: number;
  remaining_value_cents: number;
  consumed_quantity: number;
  source?: "purchase" | "adjustment" | "import";
}

export interface StoreCostRow {
  store_id: string;
  store_code: string;
  on_hand: number;
  reserved: number;
  available: number;
  weighted_average_cost_cents: number | null;
  inventory_value_cents: number;
  uncosted_quantity: number;
}

/** Current stock value and the purchase layers behind it. Realized profit is from posted sales only. */
export interface ProductCosting {
  method: "FIFO" | "WEIGHTED_AVERAGE";
  currency: string;
  default_cost_cents: number | null;
  last_purchase_cost_cents: number | null;
  weighted_average_cost_cents: number | null;
  on_hand: number;
  reserved: number;
  available: number;
  inventory_value_cents: number;
  uncosted_quantity: number;
  realized_revenue_cents: number;
  realized_cogs_cents: number;
  realized_profit_cents: number;
  layers: CostLayerRow[];
  stores: StoreCostRow[];
}

export interface ProductSerials {
  total: number;
  status_counts: Partial<Record<SerialStatus, number>>;
  rows: ProductSerialRow[];
}
