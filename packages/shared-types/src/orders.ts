import type { ComboChoice, ModifierChoice } from "./sale-item.js";

export type ServiceType = "DINE_IN" | "TAKEAWAY" | "DELIVERY";
export type OrderStatus = "OPEN" | "SETTLED" | "VOID";
export type TableStatus = "free" | "seated" | "ordered" | "bill";
export type KitchenStatus = "new" | "preparing" | "ready" | "bumped";

/** Guest-facing phase broadcast on the store table socket as `ORDER_STATUS_CHANGED`. */
export type OrderProgress = "preparing" | "ready" | "completed";

export const ORDER_PROGRESS_LABEL: Record<OrderProgress, string> = {
  preparing: "Preparing",
  ready: "Ready to Serve",
  completed: "Completed",
};

/**
 * Pushed to every screen watching `/api/v1/ws/stores/{store_id}/tables` after a round is sent
 * or a kitchen ticket moves (start, ready, bump, recall).
 */
export interface OrderStatusEvent {
  type: "ORDER_STATUS_CHANGED";
  store_id: string;
  order_id: string | null;
  table_id: string | null;
  table_label: string | null;
  ticket_id: string | null;
  /** Guest-facing phase. */
  status: OrderProgress;
  /** Line badge stored on the order, matching the kitchen ticket. */
  kitchen_status: KitchenStatus;
  item_ids: string[];
  message: string;
  updated_at: string;
}

export type GuestSuggestionKind = "usual" | "new" | "pair";

/** One dish the server can offer. `modifiers` is set only for a usual order, and nothing here is sent to the kitchen. */
export interface GuestSuggestion {
  product_id: string;
  name: string;
  price_cents: number;
  currency: string;
  kind: GuestSuggestionKind;
  pitch: string;
  modifiers: ModifierChoice[];
}

export interface GuestSuggestions {
  suggestions: GuestSuggestion[];
}

export interface OrderItemInput {
  id: string;
  product_id: string;
  quantity: number;
  unit_price_cents: number;
  modifiers?: ModifierChoice[];
  /** Meal components; each fires to its own kitchen station. */
  components?: ComboChoice[];
  seat?: number | null;
  note?: string | null;
}

export interface OrderItem extends Required<Pick<OrderItemInput, "id" | "product_id" | "quantity" | "unit_price_cents">> {
  product_name: string;
  modifiers: ModifierChoice[];
  components?: ComboChoice[];
  seat: number | null;
  note: string | null;
  sent_at: string | null;
  voided_at: string | null;
  void_reason: string | null;
  paid_sale_id: string | null;
  kitchen_status: KitchenStatus | null;
}

export interface Order {
  id: string;
  store_id: string;
  number: number;
  service_type: ServiceType;
  status: OrderStatus;
  table_id: string | null;
  table_label: string | null;
  covers: number;
  name: string | null;
  note: string | null;
  customer_id: string | null;
  opened_by_id: string;
  opened_by_name: string | null;
  revision: number;
  bill_requested_at: string | null;
  opened_at: string;
  closed_at: string | null;
  updated_at: string;
  channel_id?: string | null;
  channel_name?: string | null;
  external_ref?: string | null;
  channel_status?: string | null;
  prep_minutes?: number | null;
  items: OrderItem[];
  open_cents: number;
}

export interface DiningTable {
  id: string;
  area_id: string;
  label: string;
  seats: number;
  shape: "square" | "round" | "rect";
  x: number;
  y: number;
  w: number;
  h: number;
  is_active: boolean;
  status: TableStatus;
  order_id: string | null;
  order_number: number | null;
  covers: number;
  seated_at: string | null;
  open_cents: number;
  /** Guest name on the open tab, when the server recorded one. */
  guest_name?: string | null;
  /** Kitchen rollup of sent lines. Absent on older payloads. */
  kitchen?: "none" | "queued" | "preparing" | "partial" | "ready" | "served";
  payment?: "none" | "unpaid" | "partial" | "pending" | "paid";
  order_progress?: "none" | "draft" | "submitted" | "in_progress";
  /** Sent lines that are ready or served, and how many lines are in the kitchen. */
  kitchen_ready?: number;
  kitchen_sent?: number;
}

export interface DiningArea {
  id: string;
  store_id: string;
  name: string;
  position: number;
  is_active: boolean;
  tables: DiningTable[];
}

export interface Floor {
  store_id: string;
  areas: DiningArea[];
}

/** Lines still to pay: not voided and not settled by an earlier split check. */
export function unpaidItems(order: Pick<Order, "items">): OrderItem[] {
  return order.items.filter((item) => item.voided_at === null && item.paid_sale_id === null);
}
