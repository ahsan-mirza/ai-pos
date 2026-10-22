import { inTauri } from "../../lib/tauri";
import type { CartState } from "./cart";

async function tauriInvoke<T>(command: string, args?: Record<string, unknown>): Promise<T> {
  const core = await import("@tauri-apps/api/core");
  return core.invoke<T>(command, args);
}

export interface HeldCart {
  id: string;
  label: string;
  cashier_name: string;
  item_count: number;
  total_cents: number;
  payload: CartState;
  held_at: string;
}

const STORAGE_KEY = "ai-pos.held-carts";

/** The browser preview has no SQLite; it parks carts in localStorage so the flow can still be exercised. */
function readLocal(): HeldCart[] {
  try {
    return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]") as HeldCart[];
  } catch {
    return [];
  }
}

function writeLocal(rows: HeldCart[]): void {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(rows));
}

export async function holdCart(cart: CartState, label: string, totalCents: number, cashierName: string): Promise<void> {
  const row = {
    id: crypto.randomUUID(),
    label: label.trim(),
    item_count: cart.lines.reduce((sum, line) => sum + line.quantity, 0),
    total_cents: totalCents,
    payload: cart,
    held_at: new Date().toISOString(),
  };
  if (inTauri()) {
    await tauriInvoke("hold_cart", { input: row });
    return;
  }
  const rows = readLocal();
  if (rows.length >= 20) throw new Error("20 sales are already on hold. Recall or discard one first.");
  writeLocal([{ ...row, cashier_name: cashierName }, ...rows]);
}

export async function listHeld(): Promise<HeldCart[]> {
  if (inTauri()) return tauriInvoke<HeldCart[]>("held_carts");
  return readLocal();
}

/** Removes the cart from the hold list and returns it. */
export async function takeHeld(id: string): Promise<HeldCart | null> {
  if (inTauri()) return tauriInvoke<HeldCart | null>("recall_cart", { id });
  const rows = readLocal();
  const found = rows.find((row) => row.id === id) ?? null;
  writeLocal(rows.filter((row) => row.id !== id));
  return found;
}
