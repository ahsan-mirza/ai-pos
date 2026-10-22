import { env, previewHeaders } from "../../config/env";
import { inTauri, type CashierProfile } from "../../lib/tauri";

export type RemoteApprovalKind = "PRICE_OVERRIDE" | "BELOW_FLOOR" | "CREDIT_LIMIT" | "REFUND";
export type RemoteApprovalStatus = "PENDING" | "APPROVED" | "DECLINED" | "CANCELLED" | "EXPIRED";

/** What the register sends when it asks a manager's phone instead of a PIN at the till. */
export interface RemoteApprovalSpec {
  kind: RemoteApprovalKind;
  requestedById: string;
  title: string;
  details?: string[];
  amountCents?: number;
}

export interface RemoteApproval {
  id: string;
  status: RemoteApprovalStatus;
  expires_at: string;
  decided_by_name: string | null;
  note: string;
  approver: CashierProfile | null;
}

async function viaShell<T>(action: "create" | "get" | "cancel", body?: unknown, requestId?: string): Promise<T> {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>("approval_request", { action, body: body ?? null, requestId: requestId ?? null });
}

async function viaApi<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/approvals${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...previewHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => null);
  if (response === null) throw new Error("Remote approval needs a connection.");
  const parsed = (await response.json().catch(() => null)) as { error?: { message?: string } } | T | null;
  if (!response.ok) {
    throw new Error((parsed as { error?: { message?: string } } | null)?.error?.message ?? "The server refused the request.");
  }
  return parsed as T;
}

export function askRemoteApproval(spec: RemoteApprovalSpec): Promise<RemoteApproval> {
  const body = {
    kind: spec.kind,
    requested_by_id: spec.requestedById,
    title: spec.title.slice(0, 160),
    details: (spec.details ?? []).slice(0, 6).map((line) => line.slice(0, 200)),
    amount_cents: spec.amountCents ?? null,
    store_id: inTauri() ? null : env.storeId || null,
  };
  return inTauri() ? viaShell("create", body) : viaApi("POST", "", body);
}

export function remoteApprovalStatus(id: string): Promise<RemoteApproval> {
  return inTauri() ? viaShell("get", undefined, id) : viaApi("GET", `/${id}`);
}

export function cancelRemoteApproval(id: string): Promise<RemoteApproval> {
  return inTauri() ? viaShell("cancel", undefined, id) : viaApi("POST", `/${id}/cancel`);
}
