import type { SaleType } from "@ai-pos/shared-types";
import { inTauri, logAuditEvent, type RegisterAuditInput } from "../../lib/tauri";
import { lineGross, type CartRow } from "../checkout/cart";

/** Queues an audit event in the shell's SQLite ledger. The browser preview has no ledger, so it is a no-op there. */
export async function recordRegisterEvent(event: RegisterAuditInput): Promise<string | null> {
  if (!inTauri()) return null;
  return logAuditEvent(event);
}

const masked = (value: string) => `•••${value.slice(-4)}`;

/** A line taken off the cart before payment. IMEIs are masked: the ledger is not an IMEI store. */
export function logItemVoid(row: CartRow, mode: SaleType): void {
  const quantity = row.lines.reduce((sum, line) => sum + line.quantity, 0);
  const first = row.lines[0];
  void recordRegisterEvent({
    action_type: "ITEM_VOID",
    action: "cart.line_void",
    target_entity: "Product",
    target_entity_id: row.product.id,
    old_values: {
      sku: row.product.sku,
      name: row.product.name,
      quantity,
      unit_price_cents: first?.unitPriceCents ?? row.product.price_cents,
      line_total_cents: row.lines.reduce((sum, line) => sum + lineGross(line), 0),
      price_overridden: row.lines.some((line) => line.override !== null),
    },
    new_values: null,
    details: {
      mode,
      serials: row.lines.flatMap((line) => (line.serialValue ? [masked(line.serialValue)] : [])),
    },
  }).catch(() => undefined);
}
