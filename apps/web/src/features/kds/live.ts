import type { KitchenTicket, TicketStatus } from "@ai-pos/shared-types";
import { env } from "../../config/env";

/** Events for one station. Anything for another station never arrives on this socket. */
export interface KitchenLiveEvent {
  type: "kitchen:new-order" | "kitchen:order-updated" | "kitchen:order-cancelled" | "kitchen:status-rejected";
  station_id?: string;
  ticket?: KitchenTicket;
  ticket_id?: string;
  message?: string;
}

/**
 * Joins `station:kitchen-{stationId}` and ignores every event that is not a kitchen ticket event.
 * `onConnection` runs when the socket opens or drops so the board can reconcile.
 */
export function listenForStation(
  stationId: string,
  token: string,
  onEvent: (event: KitchenLiveEvent) => void,
  onConnection: (open: boolean) => void,
): { stop: () => void; sendStatus: (ticketId: string, status: TicketStatus | "START") => boolean } {
  let socket: WebSocket | null = null;
  let stopped = false;
  let timer = 0;
  const base = env.apiBaseUrl.replace(/^http/, "ws");
  const tenant = env.tenantDomain ? `&tenant=${encodeURIComponent(env.tenantDomain)}` : "";
  const url = `${base}/api/v1/ws/live?token=${encodeURIComponent(token)}&role=kds&station_id=${encodeURIComponent(stationId)}${tenant}`;

  const open = () => {
    if (stopped) return;
    socket = new WebSocket(url);
    socket.onopen = () => onConnection(true);
    socket.onmessage = (message) => {
      try {
        const event = JSON.parse(String(message.data)) as KitchenLiveEvent;
        if (
          event.type === "kitchen:new-order" ||
          event.type === "kitchen:order-updated" ||
          event.type === "kitchen:order-cancelled" ||
          event.type === "kitchen:status-rejected"
        ) {
          onEvent(event);
        }
      } catch {
        // A bad frame does not close the socket.
      }
    };
    socket.onclose = () => {
      if (stopped) return;
      onConnection(false);
      timer = window.setTimeout(open, 2000);
    };
  };
  open();
  return {
    stop() {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    },
    sendStatus(ticketId, status) {
      if (socket?.readyState !== WebSocket.OPEN) return false;
      socket.send(JSON.stringify({ type: "kitchen:status", ticket_id: ticketId, status }));
      return true;
    },
  };
}
