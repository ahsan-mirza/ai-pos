import { useSyncExternalStore } from "react";
import { currentShift, inTauri, type LocalShift } from "../../lib/tauri";

/** The register's open shift. Sales, returns, and drawer movements are stamped with its id. */
let shift: LocalShift | null = null;
let loaded = !inTauri();
const listeners = new Set<() => void>();

function emit(): void {
  for (const listener of listeners) listener();
}

export function activeShiftId(): string | null {
  return shift?.id ?? null;
}

export async function reloadShift(): Promise<LocalShift | null> {
  if (!inTauri()) return null;
  try {
    shift = await currentShift();
  } catch {
    shift = null;
  }
  loaded = true;
  emit();
  return shift;
}

export function setShift(next: LocalShift | null): void {
  shift = next;
  loaded = true;
  emit();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useShift(): { shift: LocalShift | null; loaded: boolean } {
  const current = useSyncExternalStore(subscribe, () => shift);
  const ready = useSyncExternalStore(subscribe, () => loaded);
  return { shift: current, loaded: ready };
}

/** Whole currency units typed by the cashier, to cents; null when the text is not an amount. */
export function parseAmount(value: string): number | null {
  const cleaned = value.replace(/,/g, "").trim();
  if (cleaned === "") return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return null;
  return Math.round(Number(cleaned) * 100);
}
