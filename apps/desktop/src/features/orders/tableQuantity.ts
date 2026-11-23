/** How a sent kitchen line may change. A reduction stays on the void flow. */
export function sentIncrease(
  current: number,
  next: number,
): { ok: true; extra: number } | { ok: false; reason: "reduce" | "invalid" | "same" } {
  if (!Number.isInteger(next) || next < 1 || next > 1000) return { ok: false, reason: "invalid" };
  if (next < current) return { ok: false, reason: "reduce" };
  if (next === current) return { ok: false, reason: "same" };
  return { ok: true, extra: next - current };
}
