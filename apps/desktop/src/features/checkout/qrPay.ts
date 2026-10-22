import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

export interface PaymentIntent {
  id: string;
  provider: string;
  amount_cents: number;
  currency: string;
  reference: string;
  qr_payload: string;
  status: "PENDING" | "PAID" | "EXPIRED" | "CANCELLED";
  expires_at: string;
}

async function viaShell(action: "create" | "get" | "cancel", intentId?: string, amountCents?: number) {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<PaymentIntent>("payment_intent", {
    action,
    intentId: intentId ?? null,
    amountCents: amountCents ?? null,
  });
}

async function viaApi(path: string, init: RequestInit = {}): Promise<PaymentIntent> {
  const response = await fetch(`${env.apiBaseUrl}/api/v1/payments/intents${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...previewHeaders() },
  });
  const body = (await response.json().catch(() => null)) as { error?: { message?: string } } | PaymentIntent | null;
  if (!response.ok) {
    throw new Error((body as { error?: { message?: string } } | null)?.error?.message ?? "QR payments need a connection.");
  }
  return body as PaymentIntent;
}

export function createIntent(amountCents: number): Promise<PaymentIntent> {
  if (inTauri()) return viaShell("create", undefined, amountCents);
  return viaApi("", { method: "POST", body: JSON.stringify({ amount_cents: amountCents, store_id: env.storeId }) });
}

export function getIntent(id: string): Promise<PaymentIntent> {
  return inTauri() ? viaShell("get", id) : viaApi(`/${id}`);
}

export function cancelIntent(id: string): Promise<PaymentIntent> {
  return inTauri() ? viaShell("cancel", id) : viaApi(`/${id}/cancel`, { method: "POST" });
}
