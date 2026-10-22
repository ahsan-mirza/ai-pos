import { env } from "../../config/env";

export interface TableEvent {
  type: "TABLE_ITEMS_ADDED" | "KDS_ITEM_READY" | "TABLE_SESSION_CLOSED" | "ORDER_STATUS_CHANGED" | string;
  store_id?: string;
  table_id?: string | null;
  table_label?: string | null;
  order_id?: string | null;
  ticket_id?: string | null;
  message?: string;
  product_name?: string;
  open_cents?: number;
  /** preparing | ready | completed */
  status?: string;
  kitchen_status?: string;
  item_ids?: string[];
  updated_at?: string;
}

/** Browser sockets cannot set headers, so the tenant and device token travel in the query. */
export function tableSocketUrl(storeId: string, token: string): string {
  const base = env.apiBaseUrl.replace(/^http/, "ws");
  const tenant = env.tenantDomain ? `&tenant=${encodeURIComponent(env.tenantDomain)}` : "";
  return `${base}/api/v1/ws/stores/${storeId}/tables?token=${encodeURIComponent(token)}${tenant}`;
}

const openSockets = new Map<string, WebSocket>();

function socketKey(storeId: string, token: string): string {
  return `${storeId}:${token}`;
}

export interface GuestTableEmit {
  tableId: string;
  tableName: string;
  totalAmount?: number;
}

/** `table:call-waiter` or `table:request-bill` on the guest socket. False when the socket is not open yet. */
export function emitTableEvent(
  storeId: string,
  token: string,
  event: "table:call-waiter" | "table:request-bill",
  payload: GuestTableEmit,
): boolean {
  const socket = openSockets.get(socketKey(storeId, token));
  if (socket === undefined || socket.readyState !== WebSocket.OPEN) return false;
  const body: GuestTableEmit & { type: string } = { type: event, tableId: payload.tableId, tableName: payload.tableName };
  if (event === "table:request-bill") body.totalAmount = payload.totalAmount ?? 0;
  socket.send(JSON.stringify(body));
  return true;
}

/** Reconnects until `stop` is called. Returns the unsubscribe function. */
export function listenForTableEvents(storeId: string, token: string, onEvent: (event: TableEvent) => void): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let timer = 0;
  const key = socketKey(storeId, token);

  const open = () => {
    if (stopped) return;
    socket = new WebSocket(tableSocketUrl(storeId, token));
    openSockets.set(key, socket);
    socket.onmessage = (message) => {
      try {
        onEvent(JSON.parse(String(message.data)) as TableEvent);
      } catch {
        // Ignore a malformed frame; the next one still arrives.
      }
    };
    socket.onclose = () => {
      if (openSockets.get(key) === socket) openSockets.delete(key);
      if (!stopped) timer = window.setTimeout(open, 2000);
    };
  };
  open();
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    if (openSockets.get(key) === socket) openSockets.delete(key);
    socket?.close();
  };
}
