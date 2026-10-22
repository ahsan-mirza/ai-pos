import type { ModifierChoice } from "./sale-item.js";

export type TicketStatus = "NEW" | "PREPARING" | "READY" | "BUMPED";

export interface KitchenStationInput {
  store_id: string;
  name: string;
  category_ids: string[];
  is_default: boolean;
  print_tickets: boolean;
  position: number;
  is_active: boolean;
}

export interface KitchenStation extends KitchenStationInput {
  id: string;
}

export interface KitchenTicketItem {
  id: string;
  order_item_id: string | null;
  product_name: string;
  quantity: number;
  modifiers: ModifierChoice[];
  /** The meal this item is part of; its other parts may be made at other stations. */
  combo_name?: string | null;
  seat: number | null;
  note: string | null;
  voided_at: string | null;
}

export interface KitchenTicket {
  id: string;
  station_id: string;
  station_name: string;
  /** The sending register prints this ticket. */
  print_tickets: boolean;
  order_id: string | null;
  sale_id: string | null;
  number: number;
  label: string;
  service_type: string;
  status: TicketStatus;
  fired_at: string;
  started_at: string | null;
  ready_at: string | null;
  bumped_at: string | null;
  updated_at: string;
  items: KitchenTicketItem[];
}

export interface KitchenBoard {
  /** Send back as `since` on the next poll to receive only what changed. */
  server_time: string;
  station: KitchenStation;
  warn_minutes: number;
  late_minutes: number;
  tickets: KitchenTicket[];
}

export const NEXT_TICKET_STATUS: Record<TicketStatus, TicketStatus | null> = {
  NEW: "PREPARING",
  PREPARING: "READY",
  READY: "BUMPED",
  BUMPED: null,
};

export type TicketAge = "fresh" | "warn" | "late";

/** Amber after `warnMinutes`, red after `lateMinutes`, counted from when the ticket fired. */
export function ticketAge(firedAt: string, now: number, warnMinutes: number, lateMinutes: number): TicketAge {
  const minutes = (now - Date.parse(firedAt)) / 60_000;
  if (minutes >= lateMinutes) return "late";
  if (minutes >= warnMinutes) return "warn";
  return "fresh";
}

/** Folds a `since` poll into the tickets on screen; bumped tickets leave the live list. */
export function mergeBoard(current: KitchenTicket[], changed: KitchenTicket[]): KitchenTicket[] {
  const byId = new Map(current.map((ticket) => [ticket.id, ticket]));
  for (const ticket of changed) byId.set(ticket.id, ticket);
  return [...byId.values()].sort((a, b) => a.fired_at.localeCompare(b.fired_at));
}
