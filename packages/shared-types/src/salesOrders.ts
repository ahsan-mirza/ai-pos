import type { PaymentMethod } from "./enums.js";

export type SalesOrderStatus =
  | "DRAFT"
  | "CONFIRMED"
  | "PICKING"
  | "PARTIALLY_DELIVERED"
  | "DELIVERED"
  | "CLOSED"
  | "CANCELLED";
export type SalesOrderSource = "manual" | "register" | "quote" | "b2b" | "ecommerce" | "rep";

export const SALES_ORDER_STATUS_LABELS: Record<SalesOrderStatus, string> = {
  DRAFT: "Draft",
  CONFIRMED: "Confirmed",
  PICKING: "Picking",
  PARTIALLY_DELIVERED: "Part delivered",
  DELIVERED: "Delivered",
  CLOSED: "Closed",
  CANCELLED: "Cancelled",
};

export const SALES_ORDER_SOURCE_LABELS: Record<SalesOrderSource, string> = {
  manual: "Portal",
  register: "Register",
  quote: "Quote",
  b2b: "B2B portal",
  ecommerce: "Web shop",
  rep: "Field rep",
};

export const OPEN_SALES_ORDER_STATUSES: readonly SalesOrderStatus[] = ["CONFIRMED", "PICKING", "PARTIALLY_DELIVERED"];

export interface SalesOrderLineInput {
  product_id: string;
  quantity: number;
  /** Omitted: the customer's tier / volume price. A lower price needs `price_approved_by_id`. */
  unit_price_cents?: number | null;
  description?: string | null;
}

export interface SalesOrderCreate {
  id?: string;
  store_id: string;
  customer_id: string;
  sale_type?: "WHOLESALE" | "RETAIL";
  lines: SalesOrderLineInput[];
  requested_date?: string | null;
  delivery_address?: string | null;
  customer_reference?: string | null;
  notes?: string | null;
  confirm?: boolean;
  price_approved_by_id?: string | null;
  credit_approved_by_id?: string | null;
  user_id?: string | null;
  source?: SalesOrderSource;
  channel_ref?: string | null;
}

export interface SalesOrderUpdate {
  lines?: SalesOrderLineInput[];
  requested_date?: string | null;
  delivery_address?: string | null;
  customer_reference?: string | null;
  notes?: string | null;
  price_approved_by_id?: string | null;
}

export interface SalesOrderLine {
  id: string;
  product_id: string;
  product_name: string;
  sku: string;
  is_serialized: boolean;
  description: string | null;
  quantity_ordered: number;
  quantity_reserved: number;
  quantity_delivered: number;
  quantity_cancelled: number;
  outstanding: number;
  /** Outstanding but not yet reserved: waiting for stock. */
  backordered: number;
  unit_price_cents: number;
  list_price_cents: number;
  tax_cents: number;
  line_total_cents: number;
  bin_location: string | null;
  available_now: number;
}

export interface PickListLine {
  order_line_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  bin_location: string | null;
}

export interface PickList {
  id: string;
  number: string;
  status: "OPEN" | "DONE" | "REPLACED";
  created_at: string;
  lines: PickListLine[];
}

export interface DeliveryNoteLine {
  order_line_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  serial_suffixes: string[];
}

export interface DeliveryNote {
  id: string;
  number: string;
  order_id: string;
  order_number: string;
  customer_name: string;
  delivery_address: string | null;
  status: "DISPATCHED" | "DELIVERED";
  sale_id: string | null;
  invoice_number: string | null;
  invoice_total_cents: number | null;
  driver_name: string | null;
  vehicle: string | null;
  dispatched_at: string;
  delivered_at: string | null;
  receiver_name: string | null;
  has_signature: boolean;
  pod_note: string | null;
  lines: DeliveryNoteLine[];
}

export interface SalesOrder {
  id: string;
  number: string;
  store_id: string;
  customer_id: string;
  customer_name: string;
  customer_type: string;
  status: SalesOrderStatus;
  sale_type: string;
  price_tier: string;
  currency: string;
  source: SalesOrderSource;
  quote_id: string | null;
  channel_ref: string | null;
  customer_reference: string | null;
  requested_date: string | null;
  delivery_address: string | null;
  notes: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  delivered_cents: number;
  created_at: string;
  confirmed_at: string | null;
  closed_at: string | null;
  lines: SalesOrderLine[];
  pick_lists: PickList[];
  deliveries: DeliveryNote[];
}

export interface SalesOrderRow {
  id: string;
  number: string;
  customer_name: string;
  status: SalesOrderStatus;
  source: SalesOrderSource;
  total_cents: number;
  currency: string;
  lines: number;
  outstanding_units: number;
  backordered_units: number;
  requested_date: string | null;
  created_at: string;
}

export interface BackorderRow {
  order_id: string;
  order_number: string;
  customer_name: string;
  product_id: string;
  product_name: string;
  sku: string;
  backordered: number;
  available_now: number;
  requested_date: string | null;
  ordered_at: string;
}

export interface DispatchLine {
  order_line_id: string;
  quantity: number;
  serials?: string[];
}

export interface DispatchInput {
  lines: DispatchLine[];
  driver_id?: string | null;
  vehicle?: string | null;
  payment_method?: PaymentMethod | null;
  credit_approved_by_id?: string | null;
}

export interface DeliverInput {
  receiver_name: string;
  /** PNG data URL drawn on the driver's phone. */
  signature?: string | null;
  note?: string | null;
}
