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
  bootstrapReadiness,
} from "../../lib/tauri";
import { capabilitiesAvailable, registerCapabilities, subscriptionHold } from "../../lib/capabilities";
import { terminal } from "../../config/terminal";
import { businessApiReachable, syncBusinessCurrency } from "./currency";
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
 * Retrying an unchanged cart keeps its number. A number is taken only after the sale is allowed to proceed. */
export async function prepareNumberedBatch(
  previous: ChargeBatch | null,
  request: ChargeRequest,
  allocate: () => Promise<string | null> = allocateInvoiceNumber,
): Promise<ChargeBatch> {
  if (previous !== null && previous.signature === cartSignature(request)) return previous;
  const invoiceNumber = await allocate();
  return prepareBatch(null, { ...request, invoiceNumber });
}

function allocateInvoiceNumber(): Promise<string | null> {
  return inTauri() ? nextDocumentNumber("INV").catch(() => null) : Promise.resolve(null);
}

export interface ChargeGate {
  pharmacyCatalog: boolean;
  offline: boolean;
  subscriptionLocked: boolean;
  profileReady: boolean;
  /** Distinguishes a stale 24-hour lease from a server-reported block. */
  hold?: "server" | "lease" | null;
  /** Rust already verified a permanent entitlement for this device. */
  entitlementValid?: boolean;
}

/** Policy gates that must pass before an invoice number is reserved. */
export function chargeGate(gate: ChargeGate): string | null {
  if (!gate.profileReady && !(gate.offline && !gate.pharmacyCatalog)) {
    return "This store's settings are not on this register yet. Connect once so they can be saved.";
  }
  const hold = gate.hold ?? (gate.subscriptionLocked ? "server" : null);
  if (hold === "server") {
    return "New sales stay closed until the subscription is verified.";
  }
  if (hold === "lease") {
    if (gate.entitlementValid === true) {
      return blockPharmacyOfflineSale(gate.pharmacyCatalog, gate.offline);
    }
    return "New sales stay closed until the subscription is verified.";
  }
  return blockPharmacyOfflineSale(gate.pharmacyCatalog, gate.offline);
}

/** Refuses a blocked sale before `allocate` runs. The register calls this with the live session. */
export async function prepareBatchAfterGate(
  previous: ChargeBatch | null,
  request: ChargeRequest,
  gate: ChargeGate,
  allocate?: () => Promise<string | null>,
): Promise<ChargeBatch | { rejected: string }> {
  const blocked = chargeGate(gate);
  if (blocked) return { rejected: blocked };
  return prepareNumberedBatch(previous, request, allocate);
}

/** Loads store settings when the API answers, then decides whether this sale can post or queue. */
async function resolveGate(): Promise<ChargeGate> {
  await syncBusinessCurrency().catch(() => undefined);
  return liveGate(!businessApiReachable());
}

async function liveGate(offline: boolean): Promise<ChargeGate> {
  const hold = subscriptionHold();
  let entitlementValid = terminal()?.entitlement_code === "VALID_PERMANENT_ENTITLEMENT";
  if (inTauri()) {
    try {
      const report = await bootstrapReadiness(capabilitiesAvailable(), hold === "server");
      entitlementValid = report.entitlement_code === "VALID_PERMANENT_ENTITLEMENT";
    } catch {
      entitlementValid = false;
    }
  }
  return {
    pharmacyCatalog: registerCapabilities().enabled.has("pharmacy_catalog"),
    offline,
    subscriptionLocked: hold !== null,
    profileReady: capabilitiesAvailable(),
    hold,
    entitlementValid,
  };
}

/** Reads the live session, refuses a blocked sale, and only then reserves an invoice number. */
export async function preparePermittedBatch(
  previous: ChargeBatch | null,
  request: ChargeRequest,
  allocate?: () => Promise<string | null>,
): Promise<ChargeBatch | { rejected: string }> {
  return prepareBatchAfterGate(previous, request, await resolveGate(), allocate);
}

export function invoiceOf(batch: ChargeBatch): string | null {
  const sale = batch.events.find((event) => event.entity_type === "sale")?.payload;
  return typeof sale?.invoice_number === "string" ? sale.invoice_number : null;
}

export const PHARMACY_OFFLINE_SALE =
  "Pharmacy medicine sales need a live connection so released lots can be checked. This sale was not saved offline.";

/** The register cache cannot tell a medicine from any other stocked line, so a pharmacy till fails closed. */
export function blockPharmacyOfflineSale(pharmacyCatalog: boolean, offline: boolean): string | null {
  if (!pharmacyCatalog || !offline) return null;
  return PHARMACY_OFFLINE_SALE;
}

/** A committed local sale stays completed. Sync status is only a label for the outbox. */
export function settleLocalSale(status: string | null | undefined, error?: string | null): ChargeOutcome {
  if (status === "synced") return { kind: "recorded" };
  const detail = error && status && status !== "pending" ? ` Sync will retry (${error}).` : "";
  return { kind: "queued", message: `Saved on this register. It will sync when the server is reachable.${detail}` };
}

export async function submitCharge(batch: ChargeBatch): Promise<ChargeOutcome> {
  if (inTauri()) {
    const blocked = chargeGate(await resolveGate());
    if (blocked) return { kind: "rejected", message: blocked };
    if (!batch.enqueued) {
      await enqueueBatch(batch.batchId, batch.events);
      batch.enqueued = true;
    }
    const status = await batchStatus(batch.batchId).catch(() => null);
    void flushSync().catch(() => undefined);
    return settleLocalSale(status?.status, status?.error ?? null);
  }

  const blocked = chargeGate(await resolveGate());
  if (blocked) return { kind: "rejected", message: blocked };
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
