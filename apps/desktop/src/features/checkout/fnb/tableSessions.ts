import type { ModifierChoice, ServiceType } from "@ai-pos/shared-types";
import { env } from "../../../config/env";
import { inTauri } from "../../../lib/tauri";
import type { CartLine } from "../cart";
import { OrderRequestError, ordersApi, queueOfflineOrder } from "../../orders/ordersClient";

export type OrderMode = "dine_in" | "takeaway" | "delivery";
export type KitchenStatus = "PENDING" | "SENT_TO_KDS" | "SERVED" | "VOIDED";
export type SessionStatus = "OPEN" | "BILL_PRINTED" | "CLOSED";

export interface SessionItem {
  id: string;
  session_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  unit_price_cents: number;
  modifiers_json: string;
  kitchen_status: KitchenStatus;
  /** Preparation note. Older saved tickets omit it. */
  note?: string | null;
}

export interface TableSession {
  id: string;
  tenant_id: string;
  store_id: string;
  table_number: string;
  guest_count: number;
  guest_name: string;
  address: string;
  phone: string;
  order_mode: OrderMode;
  status: SessionStatus;
  server_order_id: string | null;
  server_revision: number;
  created_at: string;
  updated_at: string;
  items: SessionItem[];
}

const STORAGE_KEY = "ai-pos.table-sessions";

export const FALLBACK_TABLES = ["Table 01", "Table 02", "Table 03", "Table 04", "Table 05", "Table 06", "Terrace 04"];

export function serviceTypeOf(mode: OrderMode): ServiceType {
  if (mode === "takeaway") return "TAKEAWAY";
  if (mode === "delivery") return "DELIVERY";
  return "DINE_IN";
}

/** Zones a cashier can assign when there is no zone list from the portal yet. */
export const DELIVERY_ZONES = ["Nearby", "City", "Outer", "Mall"] as const;

const META = "\u001f";

export interface TicketDetails {
  guestName: string;
  phone: string;
  address: string;
  zone: string;
  driver: string;
  pickup: string;
  tag: string;
}

/** Pack zone, driver and pickup into the address column so the register schema stays unchanged. */
export function packAddress(details: Pick<TicketDetails, "address" | "zone" | "driver" | "pickup">): string {
  if (!details.zone && !details.driver && !details.pickup) return details.address;
  return [details.address, details.zone, details.driver, details.pickup].join(META);
}

export function unpackAddress(raw: string): { address: string; zone: string; driver: string; pickup: string } {
  if (!raw.includes(META)) return { address: raw, zone: "", driver: "", pickup: "" };
  const [address = "", zone = "", driver = "", pickup = ""] = raw.split(META);
  return { address, zone, driver, pickup };
}

export function sessionHeading(session: TableSession): string {
  const guests = session.guest_count > 0 ? ` (${session.guest_count} ${session.guest_count === 1 ? "guest" : "guests"})` : "";
  const meta = unpackAddress(session.address);
  if (session.order_mode === "dine_in") return `Dine-in — ${session.table_number}${guests}`;
  if (session.order_mode === "takeaway") {
    const token = session.table_number !== "Takeaway" ? ` · #${session.table_number}` : "";
    const when = meta.pickup ? ` · ${meta.pickup}` : "";
    return `Takeaway — ${session.guest_name || "Guest"}${token}${when}`;
  }
  const zone = meta.zone ? ` · ${meta.zone}` : "";
  return `Delivery — ${session.guest_name || "Guest"}${zone}`;
}

function now(): string {
  return new Date().toISOString();
}

function readLocal(): TableSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw === null ? [] : (JSON.parse(raw) as TableSession[]);
  } catch {
    return [];
  }
}

function writeLocal(rows: TableSession[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
}

async function invoke<T>(command: string, args: Record<string, unknown>): Promise<T | null> {
  if (!inTauri()) return null;
  try {
    const core = await import("@tauri-apps/api/core");
    return await core.invoke<T>(command, args);
  } catch {
    return null;
  }
}

export async function listSessions(storeId: string): Promise<TableSession[]> {
  const remote = await invoke<TableSession[]>("list_table_sessions", { storeId });
  const rows = remote ?? readLocal();
  return rows.filter((row) => row.store_id === storeId && row.status !== "CLOSED");
}

export async function saveSession(session: TableSession): Promise<TableSession> {
  const next = { ...session, updated_at: now(), items: session.items.map((item) => ({ ...item })) };
  const saved = await invoke<TableSession>("save_table_session", { session: next });
  if (saved) return saved;
  const rows = readLocal().filter((row) => row.id !== next.id);
  rows.push(next);
  writeLocal(rows);
  return next;
}

export async function closeSession(id: string): Promise<void> {
  const closed = await invoke<boolean>("close_table_session", { id });
  if (closed !== null) return;
  writeLocal(readLocal().map((row) => (row.id === id ? { ...row, status: "CLOSED" as const, updated_at: now() } : row)));
}

export function openSession(input: {
  storeId: string;
  mode: OrderMode;
  tableNumber: string;
  guestCount: number;
  guestName?: string;
  address?: string;
  phone?: string;
  existing?: TableSession | null;
}): TableSession {
  if (input.existing && input.existing.status !== "CLOSED") {
    return {
      ...input.existing,
      guest_count: input.guestCount || input.existing.guest_count,
      guest_name: input.guestName ?? input.existing.guest_name,
      address: input.address ?? input.existing.address,
      phone: input.phone ?? input.existing.phone,
      order_mode: input.mode,
    };
  }
  const id = crypto.randomUUID();
  const stamp = now();
  return {
    id,
    tenant_id: env.tenantDomain ?? "local",
    store_id: input.storeId,
    table_number: input.tableNumber,
    guest_count: Math.max(1, input.guestCount || 1),
    guest_name: input.guestName ?? "",
    address: input.address ?? "",
    phone: input.phone ?? "",
    order_mode: input.mode,
    status: "OPEN",
    server_order_id: null,
    server_revision: 0,
    created_at: stamp,
    updated_at: stamp,
    items: [],
  };
}

/** Pending rows mirror the cart. Sent rows stay on the table after the cart is cleared. */
export function mirrorCart(session: TableSession, lines: CartLine[]): TableSession {
  const kept = session.items.filter((item) => item.kitchen_status !== "PENDING");
  const pending: SessionItem[] = lines.filter((line) => !line.orderItemId).map((line) => ({
    id: line.lineId,
    session_id: session.id,
    product_id: line.product.id,
    product_name: line.product.name,
    quantity: line.quantity,
    unit_price_cents: line.unitPriceCents,
    modifiers_json: JSON.stringify(line.modifiers ?? []),
    kitchen_status: "PENDING",
    note: line.instruction?.trim().slice(0, 160) || null,
  }));
  return { ...session, items: [...kept, ...pending] };
}

export function markSent(session: TableSession): TableSession {
  return {
    ...session,
    items: session.items.map((item) =>
      item.kitchen_status === "PENDING" ? { ...item, kitchen_status: "SENT_TO_KDS" } : item,
    ),
  };
}

export function modifiersOf(item: SessionItem): ModifierChoice[] {
  try {
    return JSON.parse(item.modifiers_json) as ModifierChoice[];
  } catch {
    return [];
  }
}

function asOrderItems(session: TableSession, ids: Set<string>) {
  return session.items
    .filter((item) => ids.has(item.id))
    .map((item) => ({
      id: item.id,
      product_id: item.product_id,
      quantity: item.quantity,
      unit_price_cents: item.unit_price_cents,
      modifiers: modifiersOf(item),
      note: item.note?.trim().slice(0, 160) || null,
    }));
}

/** Put unsent lines on the open order so they can be paid. Does not fire the kitchen. */
export async function attachForPayment(
  session: TableSession,
  userId: string,
  tableId: string | null,
  freshIds: string[],
): Promise<TableSession> {
  const ids = new Set(freshIds);
  const items = asOrderItems(session, ids);
  if (items.length === 0) return session;
  const orderId = session.server_order_id ?? session.id;
  try {
    if (session.server_order_id === null) {
      const created = await ordersApi.create(
        {
          storeId: session.store_id,
          userId,
          serviceType: serviceTypeOf(session.order_mode),
          tableId,
          covers: session.guest_count,
          name: session.guest_name || session.table_number,
          items,
        },
        session.id,
      );
      return { ...session, server_order_id: created.id, server_revision: created.revision };
    }
    const current = await ordersApi.get(session.server_order_id);
    const added = await ordersApi.addItems(current, userId, items);
    return { ...session, server_order_id: added.id, server_revision: added.revision };
  } catch (caught) {
    if (!(caught instanceof OrderRequestError) || !caught.offline) return session;
    try {
      await queueOfflineOrder(
        {
          id: orderId,
          storeId: session.store_id,
          userId,
          serviceType: serviceTypeOf(session.order_mode),
          tableId,
          covers: session.guest_count,
          name: session.guest_name || session.table_number,
          openedAt: session.created_at,
          items,
        },
        false,
      );
    } catch {
      return session;
    }
    return { ...session, server_order_id: orderId };
  }
}

/** Fire one round at the kitchen. Offline, the local ticket still records the round. */
export async function dispatchKitchen(
  session: TableSession,
  userId: string,
  tableId: string | null,
  freshIds: string[],
): Promise<TableSession> {
  const ids = new Set(freshIds);
  const items = asOrderItems(session, ids);
  if (items.length === 0) return session;
  try {
    if (session.server_order_id === null) {
      const created = await ordersApi.create(
        {
          storeId: session.store_id,
          userId,
          serviceType: serviceTypeOf(session.order_mode),
          tableId,
          covers: session.guest_count,
          name: session.guest_name || session.table_number,
          items,
        },
        session.id,
      );
      const sent = await ordersApi.send(created, userId);
      return { ...session, server_order_id: sent.id, server_revision: sent.revision };
    }
    const current = await ordersApi.get(session.server_order_id);
    const added = await ordersApi.addItems(current, userId, items);
    const sent = await ordersApi.send(added, userId);
    return { ...session, server_order_id: sent.id, server_revision: sent.revision };
  } catch {
    return session;
  }
}
