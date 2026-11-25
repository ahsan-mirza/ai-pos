import { OFFLINE_NOTICE } from "../../features/sync/connectivity";
import type { SyncState } from "./syncState";

export type StatusTone = "live" | "pending" | "offline" | "neutral";

export interface StatusChip {
  id: string;
  label: string;
  title: string;
  tone: StatusTone;
  vars?: Record<string, number>;
  /** Replaces the status dot while a sync is in progress. */
  spin?: boolean;
}

export interface StatusBarInput {
  activated: boolean;
  demo: boolean;
  desktop: boolean;
  sessionMode: "online" | "offline";
  /** False until the register API has been asked at least once. */
  apiKnown: boolean;
  apiReachable: boolean;
  /** The open page's connection reading. Null until that page publishes one. */
  page: SyncState | null;
  syncing: boolean;
  pending: number | null;
  failed: number | null;
  /** Same-key payload collisions. They are not counted as synchronized. */
  conflicts?: number | null;
  catalogSummary: string | null;
  /** Local bootstrap code from the register. Empty until it has been read. */
  readiness: string;
  /** Dataset sentence from the register. Shown while setup is incomplete. */
  readinessDetail?: string;
}

export interface StatusBarModel {
  chips: StatusChip[];
  summary: string | null;
}

function activationChip(input: StatusBarInput): StatusChip {
  if (input.demo) {
    return {
      id: "activation",
      label: "Demo",
      title: "Demo mode is active on this register.",
      tone: "pending",
    };
  }
  if (input.activated) {
    return {
      id: "activation",
      label: "Activated",
      title: "This register is activated.",
      tone: "live",
    };
  }
  return {
    id: "activation",
    label: "Not activated",
    title: "This register has not been activated.",
    tone: "offline",
  };
}

function pageRest(page: SyncState | null): string {
  if (!page || !page.label.includes(" · ")) return "";
  return page.label.split(" · ").slice(1).join(" · ");
}

function connectionChip(input: StatusBarInput): StatusChip {
  const page = input.page;
  const title = page?.title || "";
  if (input.apiKnown && !input.apiReachable) {
    return {
      id: "connection",
      label: "Offline",
      title: title || OFFLINE_NOTICE,
      tone: "offline",
    };
  }
  if (page?.label.startsWith("Connection restored") || (input.sessionMode === "offline" && input.apiReachable)) {
    return {
      id: "connection",
      label: "Connection restored",
      title: title || "The API is reachable. Sign in again to resume the online session.",
      tone: "pending",
    };
  }
  if (page?.tone === "offline" || page?.label.startsWith("Offline") || input.sessionMode === "offline") {
    return {
      id: "connection",
      label: "Offline",
      title: title || "This register is offline.",
      tone: "offline",
    };
  }
  if (!input.apiKnown && page === null) {
    return {
      id: "connection",
      label: "Checking",
      title: "Checking the connection.",
      tone: "neutral",
    };
  }
  return {
    id: "connection",
    label: "Online",
    title: title || "This register is online.",
    tone: "live",
  };
}

function queueChip(pending: number, failed: number, title: string): StatusChip {
  const detail = title || (failed > 0 ? "A sync was rejected." : "Sales are waiting to sync.");
  if (pending > 0 && failed > 0) {
    return {
      id: "queue",
      label: "Queue · {count} pending · {failed} failed",
      title: detail,
      tone: "pending",
      vars: { count: pending, failed },
    };
  }
  if (pending > 0) {
    return {
      id: "queue",
      label: "Queue · {count} pending",
      title: detail,
      tone: "pending",
      vars: { count: pending },
    };
  }
  if (failed === 1) {
    return { id: "queue", label: "Queue · 1 failed", title: detail, tone: "pending" };
  }
  return {
    id: "queue",
    label: "Queue · {failed} failed",
    title: detail,
    tone: "pending",
    vars: { failed },
  };
}

function readinessChip(code: string, activity: StatusChip | null, detail: string): StatusChip | null {
  if (code === "ONLINE_SYNC_REQUIRED" && activity?.tone !== "pending") {
    return {
      id: "readiness",
      label: "Sync required",
      title: "This register still needs an online sync.",
      tone: "pending",
    };
  }
  if (code === "BOOTSTRAP_REQUIRED") {
    return {
      id: "readiness",
      label: "Setup required",
      title: "This register has not finished its local setup.",
      tone: "pending",
    };
  }
  if (code === "BOOTSTRAP_INCOMPLETE") {
    return {
      id: "readiness",
      label: "Setup incomplete",
      title: detail || "The signed catalogue snapshot is not committed, or products, staff, or the capability snapshot are still missing.",
      tone: "pending",
    };
  }
  if (code === "REQUIRES_ONLINE_RECOVERY") {
    return {
      id: "readiness",
      label: "Recovery required",
      title: "This register needs an online recovery before it can sell.",
      tone: "offline",
    };
  }
  if (code === "ENTITLEMENT_INVALID") {
    return {
      id: "readiness",
      label: "Activation invalid",
      title: "The stored activation cannot be used. Activate this register again.",
      tone: "offline",
    };
  }
  return null;
}

function syncingChip(input: StatusBarInput): StatusChip | null {
  const syncing = input.syncing || input.catalogSummary === "Syncing catalogue…";
  if (!syncing) return null;
  return { id: "activity", label: "Syncing", title: "Syncing data.", tone: "pending", spin: true };
}

function queueStatusChip(input: StatusBarInput, connection: StatusChip): StatusChip | null {
  const title = input.page?.title || "";
  const conflicts = Math.max(0, input.conflicts ?? 0);
  if (conflicts > 0) {
    return {
      id: "queue",
      label: conflicts === 1 ? "Queue · 1 conflict" : "Queue · {conflicts} conflicts",
      title: title || "A queued sale used an existing key with a different payload. The original was not changed.",
      tone: "pending",
      ...(conflicts === 1 ? {} : { vars: { conflicts } }),
    };
  }
  const failed = Math.max(0, input.failed ?? 0);
  if (input.desktop && input.pending != null) {
    const pending = Math.max(0, input.pending);
    if (pending > 0 || failed > 0) return queueChip(pending, failed, title);
  } else {
    const rest = pageRest(input.page);
    if (rest === "Re-authenticate") {
      return { id: "activity", label: "Re-authenticate", title: title || "Sign in again to resume the online session.", tone: "pending" };
    }
    if (/pending|sync failed|queue/i.test(rest)) {
      return { id: "queue", label: "Queue", title: title || rest, tone: "pending" };
    }
  }
  if (connection.label === "Connection restored") {
    return {
      id: "activity",
      label: "Re-authenticate",
      title: title || "Sign in again to resume the online session.",
      tone: "pending",
    };
  }
  return null;
}

/** Online covers the API. Syncing and the queue appear only while data is moving or still waiting. */
export function statusBarModel(input: StatusBarInput): StatusBarModel {
  const connection = connectionChip(input);
  const syncing = syncingChip(input);
  const queue = queueStatusChip(input, connection);
  const readiness = readinessChip(input.readiness, syncing ?? queue, input.readinessDetail ?? "");
  const summary =
    input.catalogSummary && input.catalogSummary !== "Syncing catalogue…" ? input.catalogSummary : null;
  return {
    chips: [activationChip(input), connection, syncing, queue, readiness].filter((chip): chip is StatusChip => chip !== null),
    summary,
  };
}
