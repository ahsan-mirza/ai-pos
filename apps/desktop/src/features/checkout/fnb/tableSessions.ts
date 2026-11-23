import type { ModifierChoice, ServiceType } from "@ai-pos/shared-types";
import { env } from "../../../config/env";
import { inTauri } from "../../../lib/tauri";
import type { CartLine } from "../cart";
import { OrderRequestError, call, ordersApi, queueOfflineOrder } from "../../orders/ordersClient";

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
  /** Chosen serving option, JSON `{id,name,price_cents}`. Older tickets omit it. */
  price_option_json?: string | null;
  skip_recipe?: boolean;
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
  /** Session id the tag was issued for. A new ticket uses this id so the tag is not minted again. */
  sessionId?: string;
}

const PLACEHOLDER_TAGS = new Set(["", "Takeaway", "Delivery"]);
const ISSUED_TAG = /^(TW|DL)(\d{3,6}|-[A-Z0-9]{2,8}-\d{3,6})$/;

export function isPlaceholderTag(value: string): boolean {
  return PLACEHOLDER_TAGS.has(value.trim());
}

export function isIssuedTag(value: string): boolean {
  return ISSUED_TAG.test(value.trim());
}

/** An existing takeaway or delivery tag stays. A placeholder can take the tag just issued for this ticket. */
export function keptServiceTag(existing: string, incoming: string, mode: OrderMode): string {
  if (mode === "dine_in" || !isPlaceholderTag(existing)) return existing;
  const next = incoming.trim();
  return next && !isPlaceholderTag(next) ? next : existing;
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

function serviceTypeName(mode: OrderMode): "TAKEAWAY" | "DELIVERY" | null {
  if (mode === "takeaway") return "TAKEAWAY";
  if (mode === "delivery") return "DELIVERY";
  return null;
}

function browserTag(storeId: string, mode: OrderMode, sessionId: string): string {
  const key = `ai-pos.order-tags.${storeId}.${mode}`;
  let rows: Record<string, string> = {};
  try {
    rows = JSON.parse(localStorage.getItem(key) ?? "{}") as Record<string, string>;
  } catch {
    rows = {};
  }
  const current = rows[sessionId];
  if (current) return current;
  const prefix = mode === "delivery" ? "DL" : "TW";
  const used = Object.values(rows);
  const next = used.reduce((highest, tag) => {
    const value = Number(tag.split("-").at(-1));
    return Number.isFinite(value) ? Math.max(highest, value) : highest;
  }, 0) + 1;
  const tag = `${prefix}-WEB-${String(next).padStart(3, "0")}`;
  rows[sessionId] = tag;
  localStorage.setItem(key, JSON.stringify(rows));
  return tag;
}

/** One tag per session. The server sequence wins while online. Offline tags keep a device suffix and are not rewritten later. */
export async function allocateOrderTag(input: { sessionId: string; storeId: string; mode: OrderMode }): Promise<string> {
  const service = serviceTypeName(input.mode);
  if (!service) throw new Error("This order type keeps its table name.");
  const existing = await invoke<string | null>("order_tag_for_session", { sessionId: input.sessionId });
  if (existing) return existing;
  try {
    const issued = await call<{ tag: string }>("POST", "/api/v1/orders/tags", {
      id: input.sessionId,
      store_id: input.storeId,
      service_type: service,
    });
    const remembered = await invoke<string>("allocate_order_tag", {
      sessionId: input.sessionId,
      storeId: input.storeId,
      mode: input.mode,
      tag: issued.tag,
    });
    return remembered ?? issued.tag;
  } catch {
    const local = await invoke<string>("allocate_order_tag", {
      sessionId: input.sessionId,
      storeId: input.storeId,
      mode: input.mode,
    });
    if (local) return local;
    return browserTag(input.storeId, input.mode, input.sessionId);
  }
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
  id?: string;
}): TableSession {
  if (input.existing && input.existing.status !== "CLOSED") {
    const tableNumber =
      input.mode === "dine_in" || input.existing.order_mode !== input.mode
        ? input.tableNumber || input.existing.table_number
        : keptServiceTag(input.existing.table_number, input.tableNumber, input.mode);
    return {
      ...input.existing,
      table_number: tableNumber,
      guest_count: input.guestCount || input.existing.guest_count,
      guest_name: input.guestName ?? input.existing.guest_name,
      address: input.address ?? input.existing.address,
      phone: input.phone ?? input.existing.phone,
      order_mode: input.mode,
    };
  }
  const id = input.id ?? crypto.randomUUID();
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
    price_option_json: line.priceOption ? JSON.stringify(line.priceOption) : null,
    skip_recipe: line.skipRecipe === true,
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

export function priceOptionOf(item: SessionItem): { id: string; name: string; price_cents: number } | undefined {
  if (!item.price_option_json) return undefined;
  try {
    const parsed = JSON.parse(item.price_option_json) as { id?: string; name?: string; price_cents?: number };
    if (!parsed.id || !parsed.name || typeof parsed.price_cents !== "number") return undefined;
    return { id: parsed.id, name: parsed.name, price_cents: parsed.price_cents };
  } catch {
    return undefined;
  }
}

export function modifiersOf(item: SessionItem): ModifierChoice[] {
  try {
    return JSON.parse(item.modifiers_json) as ModifierChoice[];
  } catch {
    return [];
  }
}

/** Delivery phone and street address travel with the order. Zone and driver stay in the local ticket. */
export function orderHeader(session: TableSession): {
  name: string;
  covers: number;
  deliveryPhone?: string;
  deliveryAddress?: string;
} {
  const header = { name: session.guest_name || session.table_number, covers: session.guest_count };
  if (session.order_mode !== "delivery") return header;
  const phone = session.phone.trim().slice(0, 40);
  const street = unpackAddress(session.address).address.trim().slice(0, 255);
  return {
    ...header,
    ...(phone ? { deliveryPhone: phone } : {}),
    ...(street ? { deliveryAddress: street } : {}),
  };
}

function carriedTag(session: TableSession): { displayTag?: string } {
  if (session.order_mode === "dine_in" || isPlaceholderTag(session.table_number)) return {};
  return { displayTag: session.table_number };
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
      ...(priceOptionOf(item) ? { price_option_id: priceOptionOf(item)?.id } : {}),
      ...(item.skip_recipe ? { skip_recipe: true } : {}),
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
          ...orderHeader(session),
          ...carriedTag(session),
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
          ...orderHeader(session),
          ...carriedTag(session),
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
          ...orderHeader(session),
          ...carriedTag(session),
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
