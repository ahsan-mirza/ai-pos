import type { KitchenStatus, OrderMode } from "./tableSessions";

/** Reason codes the cancellation report already classifies. The label is what the cashier picks. */
export const CANCEL_REASONS = [
  ["changed_mind", "Customer changed their mind."],
  ["entry_mistake", "Customer placed order by mistake."],
  ["duplicate", "Duplicate order."],
  ["wrong_item", "Wrong items ordered."],
  ["unavailable", "Customer requested cancellation."],
  ["payment", "Payment failed or was not completed."],
  ["stock", "Item unavailable / out of stock."],
  ["operational", "Kitchen unable to fulfill order."],
  ["delivery", "Delivery unavailable."],
  ["price", "Incorrect pricing."],
  ["other", "Other."],
] as const;

export type CancelReasonCode = (typeof CANCEL_REASONS)[number][0];

export type CancelStage = "draft" | "kitchen" | "preparing" | "dispatched";

const WARNINGS: Record<Exclude<CancelStage, "draft">, string> = {
  kitchen: "This order has already been sent to the kitchen. Cancelling may require kitchen confirmation.",
  preparing: "Preparation has started. Cancellation may result in ingredient wastage.",
  dispatched: "This order has already been dispatched. Please follow the delivery cancellation process.",
};

export function sessionCancelStage(session: {
  order_mode: OrderMode;
  items: { kitchen_status: KitchenStatus }[];
}): CancelStage {
  const live = session.items.filter((item) => item.kitchen_status !== "VOIDED");
  const sent = live.some((item) => item.kitchen_status === "SENT_TO_KDS" || item.kitchen_status === "SERVED");
  if (session.order_mode === "delivery" && sent) return "dispatched";
  if (live.some((item) => item.kitchen_status === "SERVED")) return "preparing";
  if (sent) return "kitchen";
  return "draft";
}

export function cancelWarning(stage: CancelStage): string | null {
  return stage === "draft" ? null : WARNINGS[stage];
}

export function needsCancelApproval(stage: CancelStage): boolean {
  return stage !== "draft";
}

/** `[code] note`, or null when Other has no explanation. The server stores at most 160 characters. */
export function cancellationReason(code: string, note: string): string | null {
  const known = CANCEL_REASONS.find((item) => item[0] === code);
  if (!known) return null;
  const extra = note.trim();
  if (code === "other" && extra.length < 3) return null;
  const body = extra || known[1];
  return `[${code}] ${body}`.slice(0, 160);
}
