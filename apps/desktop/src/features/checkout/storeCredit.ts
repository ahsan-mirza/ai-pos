import type { StoreCreditVoucher } from "@ai-pos/shared-types";
import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

export const VOUCHER_PATTERN = /^SC-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$/;

/** Accepts what a cashier types or scans ("sc ab12 cd34 ef56", "SCAB12CD34EF56") and returns SC-XXXX-XXXX-XXXX. */
export function normalizeVoucher(raw: string): string {
  const compact = raw.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const body = compact.startsWith("SC") ? compact.slice(2) : compact;
  if (body.length !== 12) return raw.trim().toUpperCase();
  return `SC-${body.slice(0, 4)}-${body.slice(4, 8)}-${body.slice(8)}`;
}

export async function lookupVoucher(raw: string): Promise<StoreCreditVoucher> {
  const code = normalizeVoucher(raw);
  if (!VOUCHER_PATTERN.test(code)) throw new Error("Voucher codes look like SC-AB12-CD34-EF56.");
  if (inTauri()) {
    const core = await import("@tauri-apps/api/core");
    return core.invoke<StoreCreditVoucher>("store_credit_lookup", { code });
  }
  const response = await fetch(`${env.apiBaseUrl}/api/v1/store-credits/${code}`, {
    headers: previewHeaders(),
  }).catch(() => null);
  if (response === null) throw new Error("Store credit needs a connection.");
  const body = (await response.json().catch(() => null)) as { error?: { message?: string } } | StoreCreditVoucher | null;
  if (!response.ok) {
    throw new Error((body as { error?: { message?: string } } | null)?.error?.message ?? "The voucher could not be checked.");
  }
  return body as StoreCreditVoucher;
}
