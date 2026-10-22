import { env, previewHeaders } from "../../config/env";
import { inTauri } from "../../lib/tauri";
import type { CartLine } from "./cart";

export interface Floor {
  product_id: string;
  floor_cents: number;
  min_margin_bps: number;
}

async function viaShell(): Promise<Floor[]> {
  const core = await import("@tauri-apps/api/core");
  const snapshot = await core.invoke<{ floors: Floor[] }>("refresh_floors");
  return snapshot.floors;
}

async function viaApi(): Promise<Floor[]> {
  const response = await fetch(
    `${env.apiBaseUrl}/api/v1/margin/floors?store_id=${encodeURIComponent(env.storeId)}`,
    { headers: previewHeaders() },
  );
  if (!response.ok) return [];
  return (await response.json()) as Floor[];
}

/** Margin floors for this branch by product id; empty when no margin policy is set. */
export async function loadFloors(): Promise<Map<string, Floor>> {
  try {
    const rows = inTauri() ? await viaShell() : await viaApi();
    return new Map(rows.map((row) => [row.product_id, row]));
  } catch {
    return new Map();
  }
}

/** Lines priced under their floor that still need a manager's approval. */
export function linesBelowFloor(lines: CartLine[], floors: Map<string, Floor>): CartLine[] {
  return lines.filter((line) => {
    const floor = floors.get(line.product.id);
    return floor !== undefined && line.unitPriceCents < floor.floor_cents && !line.floorOverride;
  });
}
