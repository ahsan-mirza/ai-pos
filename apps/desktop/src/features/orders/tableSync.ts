import { env } from "../../config/env";
import { cacheTableEvent, inTauri, terminalApiKey } from "../../lib/tauri";

export interface TableEvent {
  type: string;
  table_id?: string | null;
  table_label?: string | null;
  message?: string;
  order_id?: string | null;
  ticket_id?: string | null;
  status?: string;
  kitchen_status?: string;
  item_ids?: string[];
  updated_at?: string;
}

function socketUrl(storeId: string): string {
  const base = env.apiBaseUrl.replace(/^http/, "ws");
  const tenant = env.tenantDomain ? `&tenant=${encodeURIComponent(env.tenantDomain)}` : "";
  return `${base}/api/v1/ws/stores/${storeId}/tables?role=pos${tenant}`;
}

/**
 * Live table events for the cashier. When the socket drops, the existing order poll keeps the
 * screen moving, and each event already received is written to the register's SQLite log.
 */
export function listenForTableEvents(storeId: string, onEvent: (event: TableEvent) => void): () => void {
  let socket: WebSocket | null = null;
  let stopped = false;
  let timer = 0;

  const open = (token: string) => {
    if (stopped) return;
    socket = new WebSocket(socketUrl(storeId));
    const openedAt = Date.now();
    socket.onopen = () => {
      socket?.send(JSON.stringify({ type: "auth", token, role: "pos" }));
    };
    socket.onmessage = (message) => {
      const raw = String(message.data);
      if (inTauri()) void cacheTableEvent(storeId, raw).catch(() => undefined);
      try {
        onEvent(JSON.parse(raw) as TableEvent);
      } catch {
        // A bad frame does not close the socket.
      }
    };
    socket.onclose = (event) => {
      // A refusal, or a socket the server drops immediately, will not succeed on the next dial.
      const refused = event.code === 1008 || (event.code !== 1001 && Date.now() - openedAt < 1500);
      if (!stopped && !refused) timer = window.setTimeout(() => void start(), 2000);
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
    socket?.close();
  };
}
