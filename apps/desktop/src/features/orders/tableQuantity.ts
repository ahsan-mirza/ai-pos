/** How a sent kitchen line may change. A reduction stays on the extra-quantity flow. */
export function sentIncrease(
  current: number,
  next: number,
): { ok: true; extra: number } | { ok: false; reason: "reduce" | "invalid" | "same" } {
  if (!Number.isInteger(next) || next < 1 || next > 1000) return { ok: false, reason: "invalid" };
  if (next < current) return { ok: false, reason: "reduce" };
  if (next === current) return { ok: false, reason: "same" };
  return { ok: true, extra: next - current };
}

export interface QuantityLine {
  id: string;
  quantity: number;
  sentAt: string | null;
  voidedAt: string | null;
  paid: boolean;
  kitchen: string | null;
  sourceId: string | null;
}

export type MinusState = "enabled" | "original" | "served" | "minimum";

export interface PresentedLine {
  key: string;
  rootId: string;
  net: number;
  /** Null until the line has been sent. */
  originalSent: number | null;
  additional: number;
  minus: MinusState;
  sent: boolean;
  served: boolean;
}

/** One card per original line. Extras linked by sourceId fold into the net quantity. */
export function presentOrderLines(items: readonly QuantityLine[]): PresentedLine[] {
  const live = items.filter((item) => item.voidedAt === null);
  const liveIds = new Set(live.map((item) => item.id));
  const extras = new Map<string, QuantityLine[]>();
  const roots: QuantityLine[] = [];
  for (const item of live) {
    if (item.sourceId && liveIds.has(item.sourceId)) {
      const rows = extras.get(item.sourceId) ?? [];
      rows.push(item);
      extras.set(item.sourceId, rows);
    } else {
      roots.push(item);
    }
  }
  return roots.map((root) => {
    const added = extras.get(root.id) ?? [];
    const additional = added.reduce((sum, line) => sum + line.quantity, 0);
    const cancellable = added.some((line) => line.kitchen !== "bumped" && !line.paid);
    const servedExtra = added.some((line) => line.kitchen === "bumped");
    const sent = root.sentAt !== null;
    let minus: MinusState = "enabled";
    if (root.paid) minus = "minimum";
    else if (!sent) minus = root.quantity > 1 ? "enabled" : "minimum";
    else if (additional > 0 && cancellable) minus = "enabled";
    else if (additional > 0 && servedExtra) minus = "served";
    else minus = "original";
    return {
      key: root.id,
      rootId: root.id,
      net: root.quantity + additional,
      originalSent: sent ? root.quantity : null,
      additional: sent ? additional : 0,
      minus,
      sent,
      served: root.kitchen === "bumped",
    };
  });
}
