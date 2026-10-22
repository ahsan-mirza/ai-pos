import type { PaymentIntent, PaymentsConfig } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

/** Card terminal and pay-later calls; the server talks to the provider, the till only starts and polls. */
async function request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
  const full = `/api/v1/payments/${path}`;
  if (inTauri()) {
    const core = await import("@tauri-apps/api/core");
    return core.invoke<T>("payments_request", { method, path: full, body: body ?? null });
  }
  const response = await fetch(`${env.apiBaseUrl}${full}`, {
    method,
    headers: { "Content-Type": "application/json", ...previewHeaders() },
    body: method === "POST" ? JSON.stringify(body ?? {}) : undefined,
  });
  const data = (await response.json().catch(() => null)) as { error?: { message?: string } } | T | null;
  if (!response.ok) {
    throw new Error((data as { error?: { message?: string } } | null)?.error?.message ?? "Card and pay-later payments need a connection.");
  }
  return data as T;
}

let cached: { at: number; config: PaymentsConfig } | null = null;
const CONFIG_TTL_MS = 60_000;

/** Terminals and pay-later providers for this store; null offline (card is then taken on the standalone machine). */
export async function loadPaymentsConfig(): Promise<PaymentsConfig | null> {
  if (cached && Date.now() - cached.at < CONFIG_TTL_MS) return cached.config;
  try {
    const query = env.storeId ? `?store_id=${encodeURIComponent(env.storeId)}` : "";
    const config = await request<PaymentsConfig>("GET", `config${query}`);
    cached = { at: Date.now(), config };
    return config;
  } catch {
    return cached?.config ?? null;
  }
}

export function startCardPayment(amountCents: number, terminalId: string | null): Promise<PaymentIntent> {
  return request("POST", "card-intents", { amount_cents: amountCents, store_id: env.storeId, terminal_id: terminalId });
}

export interface BnplStart {
  amountCents: number;
  provider: string;
  phone: string;
  name: string;
  email: string;
  items: { name: string; quantity: number; unit_cents: number; sku?: string }[];
}

export function startBnplPayment(start: BnplStart): Promise<PaymentIntent> {
  return request("POST", "bnpl-intents", {
    amount_cents: start.amountCents,
    store_id: env.storeId,
    provider: start.provider,
    customer_phone: start.phone,
    customer_name: start.name,
    customer_email: start.email,
    items: start.items,
  });
}

export function pollPayment(id: string): Promise<PaymentIntent> {
  return request("GET", `intents/${id}`);
}

export function cancelPayment(id: string): Promise<PaymentIntent> {
  return request("POST", `intents/${id}/cancel`);
}

export function simulatePayment(id: string, outcome: "approve" | "decline"): Promise<PaymentIntent> {
  return request("POST", `intents/${id}/simulate`, { outcome });
}
