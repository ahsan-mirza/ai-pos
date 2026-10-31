import { env } from "../../config/env";
import { ApiUnavailableError, listCashiers, type CashierCard } from "../../lib/api";
import { inTauri, listRegisterCashiers } from "../../lib/tauri";

export type { CashierCard };

const PREFIX = "axiz.pos.cashiers.";

export function directoryStorageKey(storeId: string): string {
  return `${PREFIX}${storeId}`;
}

/** Drops a corrupt cache. A card is a display aid, never a credential. */
export function parseDirectory(raw: string | null): CashierCard[] {
  if (raw === null || raw === "") return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return [];
  }
  if (!Array.isArray(parsed)) return [];
  return parsed.filter((row): row is CashierCard => {
    if (row === null || typeof row !== "object") return false;
    const card = row as Partial<CashierCard>;
    return typeof card.id === "string" && typeof card.display_name === "string" && typeof card.initials === "string";
  });
}

function remember(storeId: string, cards: CashierCard[]): void {
  if (typeof localStorage === "undefined") return;
  const key = directoryStorageKey(storeId);
  for (const existing of Object.keys(localStorage)) {
    if (existing.startsWith(PREFIX) && existing !== key) localStorage.removeItem(existing);
  }
  localStorage.setItem(key, JSON.stringify(cards));
}

export async function loadCashiers(): Promise<CashierCard[]> {
  if (inTauri()) return listRegisterCashiers();
  try {
    const cards = await listCashiers();
    remember(env.storeId, cards);
    return cards;
  } catch (caught) {
    if (caught instanceof ApiUnavailableError && typeof localStorage !== "undefined") {
      return parseDirectory(localStorage.getItem(directoryStorageKey(env.storeId)));
    }
    throw caught;
  }
}
