import { useEffect } from "react";
import { env } from "../../config/env";
import { getAccessToken } from "../../lib/api";
import { useStoreScope } from "../../lib/storeScope";

/** One portal socket per visible store. A processed return refreshes open sales screens without a reload. */
export function SaleReturnLive() {
  const { storeId, stores } = useStoreScope();
  const targets = storeId ? [storeId] : stores.map((store) => store.id);
  const key = targets.join(",");

  useEffect(() => {
    if (key === "") return;
    let stopped = false;
    const sockets: WebSocket[] = [];
    const timers: number[] = [];
    let refreshTimer = 0;
    const refresh = () => {
      window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => window.dispatchEvent(new CustomEvent("portal-sale-return")), 50);
    };
    const open = (store: string) => {
      if (stopped) return;
      const token = getAccessToken();
      if (!token) return;
      const base = env.apiBaseUrl.replace(/^http/, "ws");
      const tenant = env.tenantDomain ? `&tenant=${encodeURIComponent(env.tenantDomain)}` : "";
      const socket = new WebSocket(
        `${base}/api/v1/ws/live?token=${encodeURIComponent(token)}&role=portal&store_id=${encodeURIComponent(store)}${tenant}`,
      );
      sockets.push(socket);
      socket.onmessage = (message) => {
        try {
          const event = JSON.parse(String(message.data)) as { type?: string };
          if (event.type === "pos.sale_return.processed") refresh();
        } catch {
          // A bad frame does not close the socket.
        }
      };
      socket.onclose = () => {
        if (!stopped) timers.push(window.setTimeout(() => open(store), 2000));
      };
    };
    for (const store of key.split(",")) open(store);
    return () => {
      stopped = true;
      window.clearTimeout(refreshTimer);
      for (const timer of timers) window.clearTimeout(timer);
      for (const socket of sockets) socket.close();
    };
  }, [key]);

  return null;
}
