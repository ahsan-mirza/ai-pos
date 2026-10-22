import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";

/** An accepted foreign currency; rate_micros is business-currency units per foreign unit, times 1,000,000. */
export interface ForeignCurrency {
  code: string;
  name: string;
  rate_micros: number;
}

export async function loadCurrencies(): Promise<ForeignCurrency[]> {
  try {
    if (inTauri()) {
      const core = await import("@tauri-apps/api/core");
      return await core.invoke<ForeignCurrency[]>("foreign_currencies");
    }
    const response = await fetch(`${env.apiBaseUrl}/api/v1/currencies`, {
      headers: previewHeaders(),
    });
    if (!response.ok) return [];
    const rows = (await response.json()) as (ForeignCurrency & { is_active: boolean; rate_micros: number | null })[];
    return rows.filter((row) => row.is_active && row.rate_micros !== null);
  } catch {
    return [];
  }
}

/** Foreign minor units the customer must hand over to cover the total (rounded up). */
export function foreignNeeded(totalCents: number, rateMicros: number): number {
  return Math.ceil((totalCents * 1_000_000) / rateMicros);
}

/** Business-currency value of foreign cash received, rounded half up. */
export function foreignValue(receivedCents: number, rateMicros: number): number {
  return Math.floor((receivedCents * rateMicros) / 1_000_000 + 0.5);
}
