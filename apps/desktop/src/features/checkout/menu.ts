import type { ComboSlot, ModifierGroup, RegisterMenu } from "@ai-pos/shared-types";
import { useSyncExternalStore } from "react";
import { env, previewHeaders } from "../../config/env";
import { hasCapability } from "../../lib/capabilities";
import { inTauri } from "../../lib/tauri";

const EMPTY: RegisterMenu = { groups: [], products: {}, combos: {} };
let current: RegisterMenu = EMPTY;
const listeners = new Set<() => void>();

async function fetchMenu(): Promise<RegisterMenu> {
  if (inTauri()) {
    const core = await import("@tauri-apps/api/core");
    return core.invoke<RegisterMenu>("refresh_menu");
  }
  const response = await fetch(`${env.apiBaseUrl}/api/v1/menu/register`, { headers: previewHeaders() });
  return response.ok ? ((await response.json()) as RegisterMenu) : EMPTY;
}

/** Loads (or reloads) the menu modifiers; the Tauri shell falls back to its cached copy offline. */
export async function refreshMenu(): Promise<RegisterMenu> {
  if (!hasCapability("menu_modifiers")) {
    current = EMPTY;
  } else {
    try {
      current = await fetchMenu();
    } catch {
      // Keep the last menu this session saw.
    }
  }
  for (const listener of listeners) listener();
  return current;
}

export function groupsFor(menu: RegisterMenu, productId: string): ModifierGroup[] {
  const ids = menu.products[productId] ?? [];
  return ids.map((id) => menu.groups.find((group) => group.id === id)).filter((group): group is ModifierGroup => group !== undefined);
}

/** The slots of a meal, or an empty list for an ordinary item. */
export function combosFor(menu: RegisterMenu, productId: string): ComboSlot[] {
  return menu.combos?.[productId] ?? [];
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useMenu(): RegisterMenu {
  return useSyncExternalStore(subscribe, () => current);
}
