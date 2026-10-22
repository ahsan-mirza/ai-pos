import type { TradeIn, TradeInCheckResult } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

async function viaShell<T>(action: "check" | "create" | "cancel", body?: unknown, tradeInId?: string): Promise<T> {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>("trade_in_request", { action, body: body ?? null, tradeInId: tradeInId ?? null });
}

async function viaApi<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/trade-ins${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...previewHeaders() },
    body: body === undefined ? undefined : JSON.stringify(body),
  }).catch(() => null);
  if (response === null) throw new Error("Trade-ins need a connection.");
  const parsed = (await response.json().catch(() => null)) as { error?: { message?: string } } | T | null;
  if (!response.ok) {
    throw new Error((parsed as { error?: { message?: string } } | null)?.error?.message ?? "The server refused the trade-in.");
  }
  return parsed as T;
}

export function checkIdentifier(kind: "imei" | "serial", value: string): Promise<TradeInCheckResult> {
  const body = { kind, value: value.trim() };
  return inTauri() ? viaShell("check", body) : viaApi("/check", body);
}

export function createTradeIn(body: Record<string, unknown>): Promise<TradeIn> {
  return inTauri() ? viaShell("create", body) : viaApi("", body);
}

export function cancelTradeIn(id: string): Promise<TradeIn> {
  return inTauri() ? viaShell("cancel", undefined, id) : viaApi(`/${id}/cancel`);
}

/** IMEIs are 15 digits; anything else is treated as a manufacturer serial number. */
export function identifierKind(value: string): "imei" | "serial" {
  return /^\d{15}$/.test(value.trim()) ? "imei" : "serial";
}
