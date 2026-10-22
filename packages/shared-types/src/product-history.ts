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

export interface ProductSerials {
  total: number;
  status_counts: Partial<Record<SerialStatus, number>>;
  rows: ProductSerialRow[];
}
