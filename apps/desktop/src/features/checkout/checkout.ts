import type { Quote, QuoteUpsert, SyncEvent } from "@ai-pos/shared-types";
import {
  ApiRejectedError,
  ApiUnavailableError,
  createQuoteRemote,
  openQuotePdfRemote,
  pushBatch,
} from "../../lib/api";
import {
  batchStatus,
  createQuoteViaShell,
  enqueueBatch,
  flushSync,
  inTauri,
  nextDocumentNumber,
  openQuotePdfViaShell,
} from "../../lib/tauri";
import { buildChargeEvents, type ChargeRequest } from "./queue";

/** One Charge attempt. Retries of an unchanged cart reuse these idempotency keys. */
export interface ChargeBatch {
  batchId: string;
  signature: string;
  events: SyncEvent[];
  enqueued: boolean;
}

export type ChargeOutcome =
  | { kind: "recorded" }
  | { kind: "rejected"; message: string }
  | { kind: "queued"; message: string }
  | { kind: "unavailable"; message: string };

export function cartSignature(request: ChargeRequest): string {
  const { cart } = request;
  return JSON.stringify([
    request.cashierId,
    request.paymentMethod,
    request.tenders.map((tender) => [tender.method, tender.amount_cents, tender.reference, tender.gift_card_code ?? null]),
    request.creditApproval?.approvedById ?? null,
    cart.mode,
    cart.customer?.id ?? null,
    cart.associate?.id ?? null,
    cart.lines.map((line) => [
      line.product.id,
      line.quantity,
      line.unitType,
      line.unitPriceCents,
      line.listPriceCents,
      line.override?.approvedById ?? null,
      line.serialKind,
      line.serialValue,
      line.discount ? [line.discount.mode, line.discount.value, line.discount.reason, line.discount.approvedById] : null,
      line.giftCardCode ?? null,
    ]),
  ]);
}

export function prepareBatch(previous: ChargeBatch | null, request: ChargeRequest): ChargeBatch {
  const signature = cartSignature(request);
  if (previous !== null && previous.signature === signature) return previous;
  return {
    batchId: crypto.randomUUID(),
    signature,
    events: buildChargeEvents(request),
    enqueued: false,
  };
}

/** Like prepareBatch, but a new batch takes the next number from this register's offline invoice series.
 * Retrying an unchanged cart keeps its number; an abandoned attempt leaves a gap the API records. */
export async function prepareNumberedBatch(previous: ChargeBatch | null, request: ChargeRequest): Promise<ChargeBatch> {
  if (previous !== null && previous.signature === cartSignature(request)) return previous;
  const invoiceNumber = inTauri() ? await nextDocumentNumber("INV").catch(() => null) : null;
  return prepareBatch(null, { ...request, invoiceNumber });
}

export function invoiceOf(batch: ChargeBatch): string | null {
  const sale = batch.events.find((event) => event.entity_type === "sale")?.payload;
  return typeof sale?.invoice_number === "string" ? sale.invoice_number : null;
}

export async function submitCharge(batch: ChargeBatch): Promise<ChargeOutcome> {
  if (inTauri()) {
    if (!batch.enqueued) {
      await enqueueBatch(batch.batchId, batch.events);
      batch.enqueued = true;
    }
    const report = await flushSync();
    const status = await batchStatus(batch.batchId);
    if (status?.status === "synced") return { kind: "recorded" };
    if (status?.status === "rejected") {
      return { kind: "rejected", message: status.error ?? "The API rejected the sale." };
    }
    return { kind: "queued", message: report.message };
  }

  try {
    await pushBatch(batch.events);
    return { kind: "recorded" };
  } catch (error) {
    if (error instanceof ApiRejectedError) return { kind: "rejected", message: error.message };
    if (error instanceof ApiUnavailableError) return { kind: "unavailable", message: error.message };
    throw error;
  }
}

/** Quotes reserve stock on the server, so they need a live connection and are never queued. */
export async function submitQuote(payload: QuoteUpsert): Promise<Quote> {
  return inTauri() ? createQuoteViaShell(payload) : createQuoteRemote(payload);
}

export async function openQuotePdf(quote: Pick<Quote, "id" | "number">): Promise<string | null> {
  if (inTauri()) return openQuotePdfViaShell(quote.id, quote.number);
  await openQuotePdfRemote(quote.id);
  return null;
}
