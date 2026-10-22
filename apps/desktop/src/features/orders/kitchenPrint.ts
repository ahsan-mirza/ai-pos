import { renderOps, type ReceiptOp } from "@ai-pos/receipt";
import { modifierSummary, type KitchenTicket } from "@ai-pos/shared-types";
import { printRaster } from "../../lib/tauri";
import { loadPrinter } from "../printing/print";
import { ordersApi } from "./ordersClient";

const printed = new Set<string>();
// Only tickets from this send; earlier rounds of the same order were printed when they were sent.
const FRESH_MS = 2 * 60_000;

export function kitchenTicketOps(ticket: KitchenTicket, firedAt: Date = new Date(ticket.fired_at)): ReceiptOp[] {
  const time = `${String(firedAt.getHours()).padStart(2, "0")}:${String(firedAt.getMinutes()).padStart(2, "0")}`;
  const ops: ReceiptOp[] = [
    { kind: "band", text: ticket.station_name.toUpperCase(), size: 26 },
    { kind: "row", left: `#${ticket.number} ${ticket.label}`, right: time, size: 30, bold: true },
    { kind: "rule" },
  ];
  for (const item of ticket.items) {
    if (item.voided_at) continue;
    ops.push({ kind: "text", text: `${item.quantity} × ${item.product_name}${item.seat ? `  (seat ${item.seat})` : ""}`, size: 28, bold: true });
    if (item.combo_name) ops.push({ kind: "text", text: `  for ${item.combo_name}`, size: 22 });
    const modifiers = modifierSummary(item.modifiers);
    if (modifiers) ops.push({ kind: "text", text: `  ${modifiers}`, size: 24, bold: true });
    if (item.note) ops.push({ kind: "text", text: `  "${item.note}"`, size: 22 });
  }
  ops.push({ kind: "gap", height: 30 });
  return ops;
}

/**
 * Printer fallback for stations set to print: after a send, the register prints the new tickets on its own
 * thermal printer. Registers without one skip it; the kitchen screen still shows the ticket.
 */
export async function printKitchenTickets(orderId: string): Promise<void> {
  const settings = await loadPrinter();
  if (settings.transport === "none") return;
  const tickets = await ordersApi.tickets(orderId).catch(() => [] as KitchenTicket[]);
  for (const ticket of tickets) {
    const fresh = Date.now() - Date.parse(ticket.fired_at) < FRESH_MS;
    if (!ticket.print_tickets || !fresh || ticket.status === "BUMPED" || printed.has(ticket.id)) continue;
    printed.add(ticket.id);
    const rendered = await renderOps(kitchenTicketOps(ticket), settings.paper_dots);
    await printRaster({ width: rendered.width, height: rendered.height, data: rendered.bits(), kick_drawer: false }).catch(
      () => printed.delete(ticket.id),
    );
  }
}
