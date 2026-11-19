import type { SyncState } from "../../components/shell/HeaderBar";

export interface RegisterStatusInput {
  desktop: boolean;
  sessionMode: "online" | "offline";
  apiReachable: boolean;
  pending: number;
  /** Rejected sync batches. They are not part of the pending queue. */
  failed?: number;
  detail?: string;
}

/** Session mode, the settings connection, and the sync queue stay separate. An empty queue is not an online session. */
export function registerHeaderStatus(input: RegisterStatusInput): SyncState {
  const pending = Math.max(0, input.pending);
  const failed = Math.max(0, input.failed ?? 0);
  const queue = pending === 0 ? "Queue clear" : pending === 1 ? "1 pending" : `${pending} pending`;
  const title = input.detail ?? "";
  if (!input.desktop) {
    return { tone: input.apiReachable ? "live" : "offline", label: input.apiReachable ? "Live" : "Offline", title };
  }
  if (input.sessionMode === "online") {
    if (failed > 0 && pending === 0) {
      return { tone: "pending", label: failed === 1 ? "Online · 1 sync failed" : `Online · ${failed} sync failed`, title };
    }
    return {
      tone: pending > 0 ? "pending" : "live",
      label: pending > 0 ? "Online · Sync pending" : "Online · Queue clear",
      title,
    };
  }
  if (input.apiReachable) {
    const label = pending > 0 ? `Connection restored · ${queue}` : "Connection restored · Re-authenticate";
    return { tone: "pending", label, title };
  }
  return { tone: "offline", label: `Offline · ${queue}`, title };
}
