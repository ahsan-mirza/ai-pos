export interface FloorGarment {
  id: string;
  order_id: string;
  order_code: string;
  customer_name: string;
  description: string;
  stage: string;
  workflow_code: string;
  service_name: string;
  colour: string;
  fabric: string;
  condition: string;
  instructions: string;
  tag_code: string;
  hold: boolean;
  qc_result: string;
  rework_count: number;
  promised_at: string | null;
  stage_entered_at: string | null;
  operational_status: string;
  total_cents: number;
  amount_paid_cents: number;
  balance_due_cents: number;
  location: string;
}

export type ReadyFilter = "ready" | "unpaid" | "paid" | "hold" | "overdue";

export interface StageColumn {
  id: string;
  title: string;
  cards: FloorGarment[];
}

const HOUR = 60 * 60 * 1000;

function time(value: string | null): number | null {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function isOverdue(garment: FloorGarment, now: number): boolean {
  const due = time(garment.promised_at);
  if (due === null || due >= now) return false;
  return garment.operational_status !== "READY_FOR_COLLECTION" && garment.operational_status !== "COLLECTED" && garment.operational_status !== "CANCELLED";
}

export function priorityWork(garments: readonly FloorGarment[], now: number): {
  overdue: FloorGarment[];
  dueSoon: FloorGarment[];
  waiting: FloorGarment[];
  qcFailures: FloorGarment[];
  held: FloorGarment[];
} {
  return {
    overdue: garments.filter((item) => isOverdue(item, now)),
    dueSoon: garments.filter((item) => {
      const due = time(item.promised_at);
      return due !== null && due >= now && due - now <= 4 * HOUR && !isOverdue(item, now);
    }),
    waiting: garments.filter((item) => {
      const entered = time(item.stage_entered_at);
      return entered !== null && now - entered >= 2 * HOUR && item.stage !== "READY" && item.operational_status !== "READY_FOR_COLLECTION";
    }),
    qcFailures: garments.filter((item) => item.qc_result === "FAIL" || item.qc_result === "REWORK_REQUIRED"),
    held: garments.filter((item) => item.hold),
  };
}

export function stageDistribution(garments: readonly FloorGarment[]): { stage: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const garment of garments) counts.set(garment.stage, (counts.get(garment.stage) ?? 0) + 1);
  return [...counts.entries()].map(([stage, count]) => ({ stage, count }));
}

export function reworkRate(garments: readonly FloorGarment[]): number | null {
  if (garments.length === 0) return null;
  const reworked = garments.filter((item) => item.rework_count > 0).length;
  return Math.round((reworked / garments.length) * 100);
}

export function productionColumns(garments: readonly FloorGarment[], stages: readonly string[]): StageColumn[] {
  const order = stages.length > 0 ? stages : [...new Set(garments.map((item) => item.stage))];
  const known = new Set(order);
  const columns = order.map((stage) => ({
    id: stage,
    title: stage.replaceAll("_", " "),
    cards: garments.filter((item) => item.stage === stage || (stage === "READY_FOR_COLLECTION" && item.stage === "READY")),
  }));
  const extra = garments.filter((item) => !known.has(item.stage) && !(known.has("READY_FOR_COLLECTION") && item.stage === "READY"));
  if (extra.length > 0) columns.push({ id: "other", title: "Other stages", cards: extra });
  return columns.filter((column) => column.cards.length > 0 || stages.includes(column.id));
}

export function filterReady(garments: readonly FloorGarment[], filter: ReadyFilter, now: number): FloorGarment[] {
  const ready = garments.filter((item) => item.operational_status === "READY_FOR_COLLECTION" || item.stage === "READY");
  if (filter === "ready") return ready;
  if (filter === "unpaid") return ready.filter((item) => item.balance_due_cents > 0);
  if (filter === "paid") return ready.filter((item) => item.balance_due_cents === 0);
  if (filter === "hold") return ready.filter((item) => item.hold);
  return ready.filter((item) => isOverdue(item, now));
}

export function packingProgress(expected: number, scanned: number): { expected: number; scanned: number; remaining: number; complete: boolean } {
  const safeExpected = Math.max(0, expected);
  const safeScanned = Math.max(0, Math.min(scanned, safeExpected));
  const remaining = safeExpected - safeScanned;
  return { expected: safeExpected, scanned: safeScanned, remaining, complete: safeExpected > 0 && remaining === 0 };
}

export function nextActionCopy(stage: string, allowed: readonly string[], serverMessage: string): string {
  if (allowed.length > 0) return `The server allows: ${allowed.join(", ")}.`;
  if (stage === "READY") return "This garment is READY. Its production path is complete. The server allows no further move.";
  if (serverMessage.trim()) return serverMessage;
  return "The server returned no permitted move for this garment.";
}

export function recentGarments(garments: readonly FloorGarment[], limit = 5): FloorGarment[] {
  return [...garments]
    .sort((left, right) => (time(right.stage_entered_at) ?? 0) - (time(left.stage_entered_at) ?? 0))
    .slice(0, limit);
}
