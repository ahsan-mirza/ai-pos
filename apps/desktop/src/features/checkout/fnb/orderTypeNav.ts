import type { OrderMode } from "./tableSessions";

/** What Change Order Type should do before the three type cards are shown again. */
export type ChangeGate = "switch" | "confirm" | "blocked";

export function changeTypeGate(pendingLines: number, sessionLines: number, kitchen: boolean): ChangeGate {
  if (kitchen) return "blocked";
  if (pendingLines > 0 || sessionLines > 0) return "confirm";
  return "switch";
}

/** Active dining sections from the floor plan. Empty when the store has not configured any. */
export function sectionChoices(
  areas: { id: string; name: string; is_active: boolean; tables: readonly unknown[] }[],
): { id: string; name: string }[] {
  return areas
    .filter((area) => area.is_active && area.tables.length > 0)
    .map((area) => ({ id: area.id, name: area.name }));
}

export function serviceLabel(mode: OrderMode): string {
  if (mode === "takeaway") return "Takeaway";
  if (mode === "delivery") return "Delivery";
  return "Dine-in";
}
