import {
  SyncEntityType,
  SyncOperation,
  type DeliveryChannel,
  type Floor,
  type KitchenTicket,
  type Order,
  type OrderItemInput,
  type ServiceType,
} from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { enqueueBatch, inTauri } from "../../lib/tauri";

/** A refused or failed restaurant request; status 0 means the API could not be reached. */
export class OrderRequestError extends Error {
  readonly status: number;
  readonly code: string;
  readonly orderId: string | null;

  constructor(status: number, code: string, message: string, orderId: string | null = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.orderId = orderId;
  }

  get offline(): boolean {
    return this.status === 0;
  }

  get stale(): boolean {
    return this.status === 409 && this.code === "stale_order";
  }
}

/** A live request through the shell's restaurant passthrough (whitelisted paths), or fetch in the browser preview. */
export async function call<T>(method: "GET" | "POST" | "PATCH" | "PUT", path: string, body?: unknown): Promise<T> {
  if (inTauri()) {
    const core = await import("@tauri-apps/api/core");
    try {
      return await core.invoke<T>("restaurant_request", { method, path, body: body ?? null });
    } catch (caught) {
      const raw = String(caught);
      try {
        const parsed = JSON.parse(raw) as { status: number; code: string; message: string; order_id?: string };
        throw new OrderRequestError(parsed.status, parsed.code, parsed.message, parsed.order_id ?? null);
      } catch (inner) {
        if (inner instanceof OrderRequestError) throw inner;
        throw new OrderRequestError(0, "offline", raw);
      }
    }
  }
  let response: Response;
  try {
    response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...previewHeaders() },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new OrderRequestError(0, "offline", "The server is unreachable.");
  }
  const value = (await response.json().catch(() => null)) as {
    error?: { code?: string; message?: string; details?: { order_id?: string } };
  } | null;
  if (!response.ok) {
    throw new OrderRequestError(
      response.status,
      value?.error?.code ?? "rejected",
      value?.error?.message ?? "Request failed.",
      value?.error?.details?.order_id ?? null,
    );
  }
  return value as T;
}

export interface OpenOrderInput {
  storeId: string;
  userId: string;
  serviceType: ServiceType;
  tableId?: string | null;
  covers?: number;
  name?: string | null;
  items?: OrderItemInput[];
}

export const ordersApi = {
  list: (storeId: string) => call<Order[]>("GET", `/api/v1/orders?store_id=${storeId}&status=OPEN`),
  get: (id: string) => call<Order>("GET", `/api/v1/orders/${id}`),
  create: (input: OpenOrderInput, id: string = crypto.randomUUID()) =>
    call<Order>("POST", "/api/v1/orders", {
      id,
      store_id: input.storeId,
      user_id: input.userId,
      service_type: input.serviceType,
      table_id: input.tableId ?? null,
      covers: input.covers ?? 0,
      name: input.name ?? null,
      items: input.items ?? [],
    }),
  addItems: (order: Order, userId: string, items: OrderItemInput[]) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/items`, { revision: order.revision, user_id: userId, items }),
  setQuantity: (order: Order, itemId: string, userId: string, quantity: number) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/items/${itemId}/quantity`, {
      revision: order.revision,
      user_id: userId,
      quantity,
    }),
  send: (order: Order, userId: string) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/send`, { revision: order.revision, user_id: userId }),
  bill: (order: Order, userId: string) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/bill`, { revision: order.revision, user_id: userId }),
  update: (
    order: Order,
    userId: string,
    changes: {
      covers?: number;
      name?: string | null;
      note?: string | null;
      service_type?: ServiceType;
      table_id?: string | null;
      reason?: string;
    },
  ) => call<Order>("PATCH", `/api/v1/orders/${order.id}`, { revision: order.revision, user_id: userId, ...changes }),
  handOver: (order: Order, userId: string) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/hand-over`, { revision: order.revision, user_id: userId }),
  voidItem: (order: Order, itemId: string, userId: string, reason: string, approvedById: string | null) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/items/${itemId}/void`, {
      revision: order.revision,
      user_id: userId,
      reason,
      approved_by_id: approvedById,
    }),
  voidOrder: (order: Order, userId: string, reason: string, approvedById: string | null) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/void`, { revision: order.revision, user_id: userId, reason, approved_by_id: approvedById }),
  move: (order: Order, userId: string, tableId: string | null) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/move`, { revision: order.revision, user_id: userId, table_id: tableId }),
  merge: (order: Order, into: Order, userId: string) =>
    call<Order>("POST", `/api/v1/orders/${order.id}/merge`, {
      revision: order.revision,
      user_id: userId,
      into_order_id: into.id,
      into_revision: into.revision,
    }),
  floor: (storeId: string) => call<Floor>("GET", `/api/v1/dining/floor?store_id=${storeId}`),
  tickets: (orderId: string) => call<KitchenTicket[]>("GET", `/api/v1/kds/orders/${orderId}/tickets`),
};

export const channelsApi = {
  list: () => call<DeliveryChannel[]>("GET", "/api/v1/channels"),
  keyIn: (channelId: string, externalRef: string, userId: string, customerName: string | null) =>
    call<Order>("POST", "/api/v1/channels/manual-orders", {
      channel_id: channelId,
      external_ref: externalRef,
      customer_name: customerName,
      user_id: userId,
    }),
  accept: (order: Order, userId: string, prepMinutes: number) =>
    call<Order>("POST", `/api/v1/channels/orders/${order.id}/accept`, { revision: order.revision, user_id: userId, prep_minutes: prepMinutes }),
  reject: (order: Order, userId: string, reason: string) =>
    call<Order>("POST", `/api/v1/channels/orders/${order.id}/reject`, { revision: order.revision, user_id: userId, reason }),
};

/**
 * Offline: the order (or the lines added to it) is queued as an `open_order` sync event and reaches the server
 * with the next sync, where lines merge by id. Lines sent here are marked sent so the kitchen fires them on arrival.
 */
export async function queueOfflineOrder(
  input: OpenOrderInput & { id: string; openedAt?: string; note?: string | null },
  send: boolean,
): Promise<void> {
  const now = new Date().toISOString();
  const payload = {
    id: input.id,
    store_id: input.storeId,
    service_type: input.serviceType,
    table_id: input.tableId ?? null,
    covers: input.covers ?? 0,
    name: input.name ?? null,
    note: input.note ?? null,
    opened_by_id: input.userId,
    opened_at: input.openedAt ?? now,
    items: (input.items ?? []).map((item) => ({ ...item, sent_at: send ? now : null })),
  };
  await enqueueBatch(crypto.randomUUID(), [
    {
      idempotency_key: `open_order-${input.id}-${crypto.randomUUID()}`,
      entity_type: SyncEntityType.OpenOrder,
      operation: SyncOperation.Upsert,
      payload,
      occurred_at: now,
    },
  ]);
}

/** Queue a cancellation made while the register is offline. The server voids those lines on the next sync. */
export async function queueOrderVoid(input: {
  id: string;
  storeId: string;
  userId: string;
  serviceType: ServiceType;
  openedAt: string;
  reason: string;
  items: { id: string; product_id: string; quantity: number; unit_price_cents: number; sent: boolean }[];
}): Promise<void> {
  const now = new Date().toISOString();
  await enqueueBatch(crypto.randomUUID(), [
    {
      idempotency_key: `open_order-void-${input.id}-${crypto.randomUUID()}`,
      entity_type: SyncEntityType.OpenOrder,
      operation: SyncOperation.Upsert,
      payload: {
        id: input.id,
        store_id: input.storeId,
        service_type: input.serviceType,
        opened_by_id: input.userId,
        opened_at: input.openedAt,
        items: input.items.map((item) => ({
          id: item.id,
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price_cents: item.unit_price_cents,
          sent_at: item.sent ? now : null,
          voided_at: now,
          void_reason: input.reason,
        })),
      },
      occurred_at: now,
    },
  ]);
}
