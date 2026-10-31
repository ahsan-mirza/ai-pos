/** Floor presentation derived from fields the API already stores.

Occupancy is the dining-table status (`free` | `seated` | `ordered` | `bill`) plus `is_active`.
Kitchen and payment come from the open tab's sent lines, ticket statuses, paid lines, and bill request.
They are never guessed from occupancy alone.

Reservations and a cleaning state are not on the dining model, so this module does not invent them.
*/

export type KitchenPhase = "none" | "queued" | "preparing" | "partial" | "ready" | "served";
export type PaymentPhase = "none" | "unpaid" | "partial" | "pending" | "paid";
export type OrderPhase = "none" | "draft" | "submitted" | "in_progress";
export type TableTone = "available" | "occupied" | "ordered" | "preparing" | "partial" | "ready" | "served" | "payment" | "out";
export type FloorFilter = "all" | "available" | "occupied" | "preparing" | "partial" | "ready" | "served" | "payment" | "out";

export interface ServiceMarks {
  sent: number;
  /** Ticket status for each sent live line that has one: new, preparing, ready, bumped. */
  marks: string[];
  paid: number;
  unpaid: number;
  billRequested: boolean;
  hasItems: boolean;
}

export interface FloorFacts {
  active: boolean;
  status: string;
  kitchen: KitchenPhase;
  payment: PaymentPhase;
  orderProgress: OrderPhase;
}

const TONE_LABEL: Record<TableTone, string> = {
  available: "Available",
  occupied: "Occupied",
  ordered: "Order placed",
  preparing: "Preparing",
  partial: "Partially Ready",
  ready: "Ready",
  served: "Served",
  payment: "Payment",
  out: "Out of Service",
};

export const KITCHEN_LABEL: Record<KitchenPhase, string> = {
  none: "",
  queued: "Order placed",
  preparing: "Kitchen preparing",
  partial: "Partly ready",
  ready: "Ready to serve",
  served: "Served",
};

export const PAYMENT_LABEL: Record<PaymentPhase, string> = {
  none: "",
  unpaid: "Unpaid",
  partial: "Partially paid",
  pending: "Payment pending",
  paid: "Paid",
};

export const ORDER_PHASE_LABEL: Record<OrderPhase, string> = {
  none: "",
  draft: "Draft",
  submitted: "Order placed",
  in_progress: "In progress",
};

/** Same rollup the floor API uses. Keep the two copies aligned. */
export function aggregateService(input: ServiceMarks | null): Pick<FloorFacts, "kitchen" | "payment" | "orderProgress"> {
  if (input === null) return { kitchen: "none", payment: "none", orderProgress: "none" };
  let payment: PaymentPhase = "none";
  if (input.billRequested && input.unpaid > 0) payment = "pending";
  else if (input.paid > 0 && input.unpaid > 0) payment = "partial";
  else if (input.unpaid > 0) payment = "unpaid";
  else if (input.paid > 0) payment = "paid";

  const known = input.marks.filter((mark) => mark !== "");
  let kitchen: KitchenPhase = "none";
  if (input.sent === 0) kitchen = "none";
  else if (known.length === 0) kitchen = "queued";
  else if (known.length === input.sent && known.every((mark) => mark === "bumped")) kitchen = "served";
  else if (known.some((mark) => mark === "ready") && known.some((mark) => mark === "new" || mark === "preparing")) kitchen = "partial";
  else if (known.every((mark) => mark === "ready" || mark === "bumped") && known.some((mark) => mark === "ready")) kitchen = "ready";
  else if (known.some((mark) => mark === "preparing")) kitchen = "preparing";
  else kitchen = "queued";

  let orderProgress: OrderPhase = "draft";
  if (!input.hasItems || input.sent === 0) orderProgress = "draft";
  else if (kitchen === "preparing" || kitchen === "partial" || kitchen === "ready" || kitchen === "served") orderProgress = "in_progress";
  else orderProgress = "submitted";
  return { kitchen, payment, orderProgress };
}

/** One color for the whole thumbnail. Payment wins, then ready, partial, preparing, served, then a seated draft. */
export function tableTone(facts: FloorFacts): TableTone {
  if (!facts.active) return "out";
  if (facts.status === "free") return "available";
  if (facts.payment === "pending" || facts.status === "bill") return "payment";
  if (facts.kitchen === "partial") return "partial";
  if (facts.kitchen === "ready") return "ready";
  if (facts.kitchen === "preparing" || facts.kitchen === "queued") return "preparing";
  if (facts.kitchen === "served") return "served";
  if (facts.status === "ordered") return "preparing";
  return "occupied";
}

export function toneLabel(tone: TableTone): string {
  return TONE_LABEL[tone];
}

export interface FloorMatch {
  key: string;
  areaId: string;
  search: string;
  active: boolean;
  status: string;
  kitchen: KitchenPhase;
  payment: PaymentPhase;
}

export function matchesFloorFilter(filter: FloorFilter, item: FloorMatch): boolean {
  if (filter === "all") return true;
  const tone = tableTone({
    active: item.active,
    status: item.status,
    kitchen: item.kitchen,
    payment: item.payment,
    orderProgress: "none",
  });
  return tone === filter;
}

export function floorCounts(items: FloorMatch[]): Record<FloorFilter, number> {
  const filters: FloorFilter[] = ["all", "available", "occupied", "preparing", "partial", "ready", "served", "payment", "out"];
  return Object.fromEntries(filters.map((filter) => [filter, items.filter((item) => matchesFloorFilter(filter, item)).length])) as Record<
    FloorFilter,
    number
  >;
}
