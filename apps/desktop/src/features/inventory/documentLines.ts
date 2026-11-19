/** Line lists for the register's purchase orders, receipts, and transfers.
 * The payloads match the existing inventory API. A document is one request, not one request per product.
 */

export interface DraftLine {
  key: string;
  productId: string;
  quantity: string;
  cost: string;
}

export interface PurchaseLine {
  product_id: string;
  quantity_ordered: number;
  unit_cost_cents: number;
}

export interface TransferLine {
  product_id: string;
  quantity: number;
}

export interface ReceiptSource {
  id: string;
  name: string;
  quantity_ordered: number;
  quantity_received: number;
  lot_controlled?: boolean;
}

export interface ReceiptDraft {
  quantity: string;
  lot: string;
  expiry: string;
}

export interface ReceiptLine {
  purchase_order_line_id: string;
  quantity: number;
  manufacturer_lot: string | null;
  expiry_date: string | null;
}

export function blankLine(key: string): DraftLine {
  return { key, productId: "", quantity: "1", cost: "0" };
}

export function moneyToCents(value: string): number | null {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount < 0) return null;
  const cents = Math.round(amount * 100);
  if (!Number.isSafeInteger(cents)) return null;
  return cents;
}

function wholeQuantity(value: string): number | null {
  const quantity = Number(value);
  if (!Number.isInteger(quantity) || quantity < 1) return null;
  return quantity;
}

function uniqueProducts(lines: DraftLine[]): string | null {
  const ids = lines.map((line) => line.productId);
  if (ids.some((id) => id.trim() === "")) return "Choose a product on every line.";
  if (new Set(ids).size !== ids.length) return "Each product can appear only once on this document.";
  return null;
}

export function purchaseOrderLines(lines: DraftLine[]): { lines: PurchaseLine[] } | { error: string } {
  if (lines.length === 0) return { error: "Add at least one product." };
  const duplicate = uniqueProducts(lines);
  if (duplicate) return { error: duplicate };
  const payload: PurchaseLine[] = [];
  for (const line of lines) {
    const quantity = wholeQuantity(line.quantity);
    const cost = moneyToCents(line.cost);
    if (quantity === null) return { error: "Each quantity must be a whole number of at least 1." };
    if (cost === null) return { error: "Each unit cost must be zero or more." };
    payload.push({ product_id: line.productId, quantity_ordered: quantity, unit_cost_cents: cost });
  }
  return { lines: payload };
}

export function transferLines(
  sourceId: string,
  destinationId: string,
  lines: DraftLine[],
): { lines: TransferLine[] } | { error: string } {
  if (sourceId === "" || destinationId === "") return { error: "Choose the source and destination stores." };
  if (sourceId === destinationId) return { error: "Source and destination must be different stores." };
  if (lines.length === 0) return { error: "Add at least one product." };
  const duplicate = uniqueProducts(lines);
  if (duplicate) return { error: duplicate };
  const payload: TransferLine[] = [];
  for (const line of lines) {
    const quantity = wholeQuantity(line.quantity);
    if (quantity === null) return { error: "Each quantity must be a whole number of at least 1." };
    payload.push({ product_id: line.productId, quantity });
  }
  return { lines: payload };
}

export function receiptLines(
  sources: ReceiptSource[],
  drafts: Record<string, ReceiptDraft>,
  pharmacy: boolean,
): { lines: ReceiptLine[] } | { error: string } {
  const lines: ReceiptLine[] = [];
  for (const source of sources) {
    const outstanding = source.quantity_ordered - source.quantity_received;
    if (outstanding <= 0) continue;
    const draft = drafts[source.id] ?? { quantity: String(outstanding), lot: "", expiry: "" };
    const quantity = Number(draft.quantity);
    if (draft.quantity.trim() === "" || quantity === 0) continue;
    if (!Number.isInteger(quantity) || quantity < 1) {
      return { error: `${source.name} needs a whole quantity.` };
    }
    if (quantity > outstanding) {
      return { error: `${source.name} has only ${outstanding} left to receive.` };
    }
    const lotControlled = pharmacy && source.lot_controlled === true;
    const lot = draft.lot.trim();
    if (lotControlled && (lot === "" || draft.expiry === "")) {
      return { error: `Enter the manufacturer lot and expiry for ${source.name}.` };
    }
    lines.push({
      purchase_order_line_id: source.id,
      quantity,
      manufacturer_lot: lotControlled ? lot : null,
      expiry_date: lotControlled ? draft.expiry : null,
    });
  }
  if (lines.length === 0) return { error: "Enter at least one quantity to receive." };
  return { lines };
}
