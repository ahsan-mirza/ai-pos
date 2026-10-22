import { env } from "../../config/env";
import { terminalApiKey } from "../../lib/tauri";

export interface PosTableAlert {
  id: string;
  alert: "call-waiter" | "request-bill";
  tableId: string;
  tableName: string;
  totalAmount: number | null;
  createdAt: string;
}

export type PosAlertMessage =
  | { type: "alert"; alert: PosTableAlert }
  | { type: "cleared"; alertId: string; tableId: string };

let posSocket: WebSocket | null = null;

function socketUrl(storeId: string, token: string): string {
  const base = env.apiBaseUrl.replace(/^http/, "ws");
  const tenant = env.tenantDomain ? `&tenant=${encodeURIComponent(env.tenantDomain)}` : "";
  return `${base}/api/v1/ws/stores/${storeId}/tables?token=${encodeURIComponent(token)}&role=pos${tenant}`;
}

function readAlert(raw: unknown): PosAlertMessage | null {
  if (raw === null || typeof raw !== "object") return null;
  const event = raw as Record<string, unknown>;
  if (event.type === "pos:table-alert-cleared") {
    const alertId = typeof event.alertId === "string" ? event.alertId : "";
    const tableId = typeof event.tableId === "string" ? event.tableId : "";
    return alertId && tableId ? { type: "cleared", alertId, tableId } : null;
  }
  if (event.type !== "pos:table-alert") return null;
  const alert = event.alert === "call-waiter" || event.alert === "request-bill" ? event.alert : null;
  const id = typeof event.id === "string" ? event.id : "";
  const tableId = typeof event.tableId === "string" ? event.tableId : "";
  if (alert === null || id === "" || tableId === "") return null;
  return {
    type: "alert",
    alert: {
      id,
      alert,
      tableId,
      tableName: typeof event.tableName === "string" && event.tableName.trim() !== "" ? event.tableName : "Table",
      totalAmount: typeof event.totalAmount === "number" ? event.totalAmount : null,
      createdAt: typeof event.createdAt === "string" ? event.createdAt : new Date().toISOString(),
    },
  };
}

/** Register socket in `pos:terminals:{storeId}`. Reconnects until the caller stops it. */
export function listenForPosAlerts(storeId: string, onEvent: (event: PosAlertMessage) => void): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let timer = 0;

  const open = (token: string) => {
    if (stopped) return;
    socket = new WebSocket(socketUrl(storeId, token));
    posSocket = socket;
    socket.onmessage = (message) => {
      try {
        const parsed = readAlert(JSON.parse(String(message.data)));
        if (parsed) onEvent(parsed);
      } catch {
        // A bad frame does not close the socket.
      }
    };
    socket.onclose = () => {
      if (posSocket === socket) posSocket = null;
      if (!stopped) timer = window.setTimeout(() => void start(), 2000);
    };
  };

  const start = async () => {
    const token = (await terminalApiKey().catch(() => null)) || env.apiKey;
    if (!token || stopped) return;
    open(token);
  };
  void start();
  return () => {
    stopped = true;
    window.clearTimeout(timer);
    if (posSocket === socket) posSocket = null;
    socket?.close();
  };
}

export function sendPosAlertAck(alertId: string, tableId: string): void {
  if (posSocket === null || posSocket.readyState !== WebSocket.OPEN) return;
  posSocket.send(JSON.stringify({ type: "pos:table-alert-ack", alertId, tableId }));
}
