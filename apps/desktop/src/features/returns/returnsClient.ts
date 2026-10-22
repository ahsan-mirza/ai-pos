import { Permission, type Receipt, type SyncEvent } from "@ai-pos/shared-types";
import { ApiRejectedError, ApiUnavailableError, loginPin, lookupReceipt, pushBatch } from "../../lib/api";
import {
  approveReturn,
  batchStatus,
  enqueueReturn,
  flushSync,
  inTauri,
  lookupReceiptViaShell,
  type CashierProfile,
} from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { loadCatalog } from "../checkout/catalog";
import type { ChargeOutcome } from "../checkout/checkout";
import { applyLocalReturns, receiptFromQueuedSale } from "./returnMath";

export interface LoadedReceipt {
  receipt: Receipt;
  source: "api" | "cache" | "register";
  message: string | null;
  /** Full identifiers for sales rung up on this register; synced receipts only expose the last four. */
  serials: Record<string, string>;
}

export async function findReceipt(code: string): Promise<LoadedReceipt> {
  const trimmed = code.trim();
  if (!inTauri()) {
    return { receipt: await lookupReceipt(trimmed), source: "api", message: null, serials: {} };
  }
  const found = await lookupReceiptViaShell(trimmed);
  if (found.receipt !== null) {
    return {
      receipt: applyLocalReturns(found.receipt, found.local_returns),
      source: found.source,
      message: found.message,
      serials: {},
    };
  }
  if (found.queued_sale === null) throw new Error("No sale matches that receipt.");
  const sale = found.queued_sale;
  const { products } = await loadCatalog();
  const receipt = applyLocalReturns(receiptFromQueuedSale(sale, products, new Date()), found.local_returns);
  const serials: Record<string, string> = {};
  for (const item of sale.items) {
    if (item.serial_value !== null) serials[item.id] = item.serial_value;
  }
  return { receipt, source: "register", message: found.message, serials };
}

/** Tauri checks the PIN online first, then the cached hash; the browser preview is online only. */
export async function verifyApprover(session: CashierSession, username: string, pin: string): Promise<CashierProfile> {
  if (inTauri()) return approveReturn(username.trim().toLowerCase(), pin);
  const { user } = await loginPin(username.trim().toLowerCase(), pin);
  if (user.id === session.user.id) throw new Error("Approval must come from a different staff member.");
  if (!user.permissions.includes(Permission.PosRefund)) throw new Error(`${user.full_name} cannot approve refunds.`);
  if (user.store_id !== null && session.user.store_id !== null && user.store_id !== session.user.store_id) {
    throw new Error(`${user.full_name} is not assigned to this store.`);
  }
  return {
    id: user.id,
    username: user.username,
    full_name: user.full_name,
    store_id: user.store_id,
    role_name: user.role.name,
    permissions: user.permissions,
  };
}

/** One Refund attempt. Retrying an unchanged return reuses its idempotency key and store credit code. */
export interface ReturnBatch {
  batchId: string;
  signature: string;
  events: SyncEvent[];
  creditCode: string;
  enqueued: boolean;
}

export async function submitReturn(batch: ReturnBatch): Promise<ChargeOutcome> {
  if (inTauri()) {
    if (!batch.enqueued) {
      await enqueueReturn(batch.batchId, batch.events);
      batch.enqueued = true;
    }
    const report = await flushSync();
    const status = await batchStatus(batch.batchId);
    if (status?.status === "synced") return { kind: "recorded" };
    if (status?.status === "rejected") {
      return { kind: "rejected", message: status.error ?? "The API rejected the return." };
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
