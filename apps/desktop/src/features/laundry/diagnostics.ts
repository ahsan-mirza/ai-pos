import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { inTauri } from "../../lib/tauri";
import { currentAccessToken } from "../auth/session";
import { OFFLINE_PRODUCTION } from "./productionAccess";

export type NoticeTone = "session" | "offline" | "sync" | "error" | "ok";

export type NoticeKind =
  | "unauthenticated"
  | "forbidden"
  | "missing"
  | "validation"
  | "server"
  | "offline"
  | "sync"
  | "rejected"
  | "ok";

export interface FloorNotice {
  tone: NoticeTone;
  title: string;
  detail: string;
  requestId: string;
  canRetry: boolean;
  kind?: NoticeKind;
  /** Server sentence kept for support. It is not the banner title. */
  serverMessage?: string;
}

export type DashboardPhase = "signed-out" | "loading" | "permission" | "offline" | "failure" | "empty" | "ready";

/** What the dashboard may draw. An empty board is only "empty" after a successful load. */
export function dashboardPhase(input: {
  signedIn: boolean;
  /** Offline unlock has a cashier and no access token. That is not a loaded board. */
  offlineSession?: boolean;
  loaded: boolean;
  garmentCount: number;
  notice: FloorNotice | null;
}): DashboardPhase {
  if (input.offlineSession) return "offline";
  if (!input.signedIn) return "signed-out";
  if (!input.loaded && input.notice?.kind === "forbidden") return "permission";
  if (!input.loaded && (input.notice?.kind === "offline" || input.notice?.tone === "offline")) return "offline";
  if (!input.loaded && input.notice && input.notice.kind !== "ok" && input.notice.tone !== "ok") return "failure";
  if (!input.loaded) return "loading";
  if (input.garmentCount === 0) return "empty";
  return "ready";
}

/** The API uses 403 for a device principal. That sentence is a missing user, not a role denial. */
export function missingUserSession(status: number, code: string, message: string): boolean {
  if (status >= 500) return false;
  if (status === 401 || code === "authentication_required" || code === "locked" || code === "unauthorized" || code === "invalid_token") {
    return true;
  }
  return status === 403 && /requires a signed-in user/i.test(message);
}

function notice(partial: FloorNotice): FloorNotice {
  return partial;
}

/** Split a failed laundry call by HTTP status. A reachable API is not a signed-in session. */
export function noticeFromError(error: unknown, source: "sync" | "action" = "action"): FloorNotice {
  if (error instanceof RetailRequestError && error.offline) {
    return notice({
      tone: "offline",
      kind: "offline",
      title: "The register cannot reach the server",
      detail: OFFLINE_PRODUCTION,
      requestId: "",
      canRetry: true,
    });
  }
  const message = error instanceof Error ? error.message : "The laundry floor could not complete that action.";
  const code = error instanceof RetailRequestError ? error.code : "";
  const status = error instanceof RetailRequestError ? error.status : 0;
  const requestId = error instanceof RetailRequestError ? error.requestId : "";
  if (status >= 500) {
    return notice({
      tone: "error",
      kind: "server",
      title: "The laundry service failed",
      detail: "The laundry service had a problem answering this request. The register session was not signed out.",
      serverMessage: message,
      requestId,
      canRetry: true,
    });
  }
  if (missingUserSession(status, code, message)) {
    return notice({
      tone: "session",
      kind: "unauthenticated",
      title: "Unlock the register",
      detail: "This window has no signed-in access token. Unlock the register, then this request can run again. A cashier name on screen is not a session.",
      serverMessage: message,
      requestId,
      canRetry: false,
    });
  }
  if (status === 403) {
    return notice({
      tone: "error",
      kind: "forbidden",
      title: "This action is not permitted",
      detail: message || "This signed-in user does not have permission for this action.",
      requestId,
      canRetry: false,
    });
  }
  if (status === 404) {
    return notice({
      tone: "error",
      kind: "missing",
      title: "That record was not found",
      detail: message,
      requestId,
      canRetry: false,
    });
  }
  if (status === 422) {
    return notice({
      tone: "error",
      kind: "validation",
      title: "Those details were not accepted",
      detail: message,
      requestId,
      canRetry: false,
    });
  }
  if (source === "sync") {
    return notice({
      tone: "sync",
      kind: "sync",
      title: "Synchronization failed",
      detail: message,
      requestId,
      canRetry: true,
    });
  }
  return notice({
    tone: "error",
    kind: "rejected",
    title: "The server did not accept that action",
    detail: message,
    requestId,
    canRetry: true,
  });
}

/**
 * A visible cashier is not a session.
 * The browser must hold an access token in memory.
 * The native shell holds that token for an online unlock. An offline unlock has none.
 */
export function registerSignedIn(mode?: "online" | "offline" | null): boolean {
  if (currentAccessToken() !== null) return true;
  return inTauri() && mode === "online";
}

/**
 * Laundry calls go through the shared retail client. Without a token the browser must not send them.
 * The native shell attaches its own session inside the register process.
 */
export async function laundryCall<T>(
  method: "GET" | "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  body?: unknown,
): Promise<T> {
  // The native shell attaches its own token and refuses a laundry route before the network when that token is missing.
  if (currentAccessToken() === null && !inTauri()) {
    throw new RetailRequestError(401, "authentication_required", "This action requires a signed-in user.");
  }
  return retailCall<T>(method, path, body);
}

export function sessionHeadline(hasToken: boolean): FloorNotice {
  if (hasToken) {
    return notice({
      tone: "ok",
      kind: "ok",
      title: "Signed in",
      detail: "This window has an access token.",
      requestId: "",
      canRetry: false,
    });
  }
  return notice({
    tone: "session",
    kind: "unauthenticated",
    title: "Unlock the register",
    detail: "This window has no access token. The cashier profile can remain after a refresh, and a reachable API does not replace that token.",
    requestId: "",
    canRetry: false,
  });
}
