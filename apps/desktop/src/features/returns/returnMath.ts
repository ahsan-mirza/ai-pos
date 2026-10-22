import seed from "@ai-pos/catalog/seed.json";
import {
  OverrideReason,
  PaymentMethod,
  Permission,
  RefundMethod,
  SyncEntityType,
  SyncOperation,
  discountShareCents,
  policyConditions,
  proratedTaxCents,
  restockingFeeCents,
  weighedLineCents,
  type ProductUpsert,
  type Receipt,
  type ReceiptItem,
  type ReturnCondition,
  type ReturnConditionRule,
  type ReturnPolicy,
  type ReturnReason,
  type ReturnUpsert,
  type SaleUpsert,
  type SerialKind,
  type SyncEvent,
} from "@ai-pos/shared-types";
import { posPolicy } from "../../lib/capabilities";
import type { LocalReturn } from "../../lib/tauri";

export const returnPolicy = seed.return_policy as ReturnPolicy;

/** The business's returns policy from the cached till rules (the bundled seed before the first sync). */
export function localReturnPolicy(): ReturnPolicy {
  const rules = posPolicy().returns;
  if (!rules?.conditions?.length) return returnPolicy;
  return {
    window_days: rules.window_days,
    exchange_window_days: rules.exchange_window_days,
    open_box_fee_bps: rules.conditions.find((condition) => condition.key === "open_box")?.fee_bps ?? 0,
    serial_status_by_condition: Object.fromEntries(rules.conditions.map((condition) => [condition.key, condition.serial_status])),
    preset: rules.preset,
    conditions: rules.conditions,
    reasons: rules.reasons,
  };
}

export function conditionRule(policy: ReturnPolicy, key: ReturnCondition): ReturnConditionRule | undefined {
  return policyConditions(policy).find((condition) => condition.key === key);
}

const DAY_MS = 24 * 60 * 60 * 1000;
const CREDIT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

export function invoiceNumber(clientSaleId: string): string {
  return clientSaleId.slice(0, 8).toUpperCase();
}

/** A sale rung up on this register that has not reached the API yet. */
export function receiptFromQueuedSale(sale: SaleUpsert, products: ProductUpsert[], soldAt: Date): Receipt {
  const byId = new Map(products.map((product) => [product.id, product]));
  return {
    sale_id: sale.id,
    invoice: invoiceNumber(sale.client_sale_id),
    store_id: sale.store_id,
    cashier_id: sale.cashier_id,
    status: "completed",
    currency: sale.currency,
    payment_method: sale.payment_method,
    subtotal_cents: sale.subtotal_cents,
    tax_cents: sale.tax_cents,
    total_cents: sale.total_cents,
    refunded_cents: 0,
    card_refundable_cents: sale.payment_method === PaymentMethod.Card ? sale.total_cents : 0,
    created_at: soldAt.toISOString(),
    policy: localReturnPolicy(),
    items: sale.items.map((item) => {
      const product = byId.get(item.product_id);
      return {
        sale_item_id: item.id,
        product_id: item.product_id,
        sku: product?.sku ?? "—",
        name: product?.name ?? "Product not in the local catalog",
        category: product?.category ?? "Other",
        is_serialized: item.serial_value !== null,
        serial_kind: item.serial_kind,
        serial_last4: item.serial_value?.slice(-4) ?? null,
        quantity: item.quantity,
        returned_quantity: 0,
        unit_price_cents: item.unit_price_cents,
        tax_cents: item.tax_cents,
        refunded_tax_cents: 0,
        line_total_cents: item.line_total_cents,
        sold_by_weight: product?.sold_by_weight ?? false,
        discount_cents: (item.discount_cents ?? 0) + (item.manual_discount_cents ?? 0),
        gift_card: Boolean(item.gift_card_code),
        variant: Object.values(product?.variant_attributes ?? {}).join(" · ") || null,
      };
    }),
  };
}

/** Subtracts returns made on this register that the receipt does not reflect yet. */
export function applyLocalReturns(receipt: Receipt, local: LocalReturn[]): Receipt {
  if (local.length === 0) return receipt;
  const items = receipt.items.map((item) => ({ ...item }));
  const byId = new Map(items.map((item) => [item.sale_item_id, item]));
  let refunded = receipt.refunded_cents;
  let cardRefundable = receipt.card_refundable_cents;
  for (const entry of local) {
    refunded += entry.payload.total_refund_cents;
    for (const tender of entry.payload.tenders) {
      if (tender.method === RefundMethod.OriginalCard) cardRefundable -= tender.amount_cents;
    }
    for (const line of entry.payload.items) {
      const item = byId.get(line.sale_item_id);
      if (item === undefined) continue;
      item.returned_quantity += line.quantity;
      item.refunded_tax_cents += line.tax_refund_cents;
    }
  }
  const fullyReturned = items.every((item) => item.returned_quantity >= item.quantity);
  return {
    ...receipt,
    items,
    refunded_cents: refunded,
    card_refundable_cents: Math.max(0, cardRefundable),
    status: fullyReturned ? "refunded" : "partially_refunded",
  };
}

export function remainingQuantity(item: ReceiptItem): number {
  return Math.max(0, item.quantity - item.returned_quantity);
}

export function daysSinceSale(receipt: Receipt, now: Date): number {
  return Math.floor((now.getTime() - new Date(receipt.created_at).getTime()) / DAY_MS);
}

function ageMs(receipt: Receipt, now: Date): number {
  return now.getTime() - new Date(receipt.created_at).getTime();
}

/** Past the refund window and the exchange window: only a manager can accept it. Mirrors the API. */
export function isOutsideWindow(receipt: Receipt, now: Date): boolean {
  const { window_days, exchange_window_days = 0 } = receipt.policy;
  return ageMs(receipt, now) > (window_days + exchange_window_days) * DAY_MS;
}

/** Past the refund window but inside the exchange window: the refund goes to an exchange voucher only. */
export function isExchangeOnly(receipt: Receipt, now: Date): boolean {
  const { window_days, exchange_window_days = 0 } = receipt.policy;
  const age = ageMs(receipt, now);
  return age > window_days * DAY_MS && age <= (window_days + exchange_window_days) * DAY_MS;
}

export interface LineDraft {
  quantity: number;
  condition: ReturnCondition;
  reason: ReturnReason;
  serialValue: string | null;
  serialKind: SerialKind | null;
}

export interface PricedLine {
  item: ReceiptItem;
  draft: LineDraft;
  subtotal: number;
  tax: number;
  policyFee: number;
  fee: number;
  refund: number;
}

export function priceLines(receipt: Receipt, drafts: Record<string, LineDraft>, waiveFee: boolean): PricedLine[] {
  return receipt.items.flatMap((item) => {
    const draft = drafts[item.sale_item_id];
    if (draft === undefined) return [];
    // Weighed lines count grams at a per-kg price (mirrors app/services/weighed.py).
    const gross = item.sold_by_weight
      ? weighedLineCents(draft.quantity, item.unit_price_cents)
      : item.unit_price_cents * draft.quantity;
    // Returned units carry their share of the line's promotion and cashier discount (mirrors discount_share).
    const subtotal =
      gross - discountShareCents(item.discount_cents ?? 0, item.quantity, draft.quantity, item.returned_quantity);
    const tax = proratedTaxCents(
      item.tax_cents,
      item.quantity,
      draft.quantity,
      item.returned_quantity,
      item.refunded_tax_cents,
    );
    const feeBps = conditionRule(receipt.policy, draft.condition)?.fee_bps ?? 0;
    const policyFee = item.sold_by_weight
      ? restockingFeeCents(gross, 1, feeBps)
      : restockingFeeCents(item.unit_price_cents, draft.quantity, feeBps);
    const fee = waiveFee ? 0 : policyFee;
    return [{ item, draft, subtotal, tax, policyFee, fee, refund: subtotal + tax - fee }];
  });
}

export interface ReturnTotals {
  subtotal: number;
  tax: number;
  policyFee: number;
  fee: number;
  total: number;
}

export function returnTotals(lines: PricedLine[]): ReturnTotals {
  const sum = (pick: (line: PricedLine) => number) => lines.reduce((total, line) => total + pick(line), 0);
  return {
    subtotal: sum((line) => line.subtotal),
    tax: sum((line) => line.tax),
    policyFee: sum((line) => line.policyFee),
    fee: sum((line) => line.fee),
    total: sum((line) => line.refund),
  };
}

/** Mirrors the server: each reason here must be covered by a manager approval. */
export function requiredOverrides(
  receipt: Receipt,
  lines: PricedLine[],
  permissions: string[],
  now: Date,
): OverrideReason[] {
  const reasons: OverrideReason[] = [];
  if (!permissions.includes(Permission.PosRefund)) reasons.push(OverrideReason.NoRefundPermission);
  if (isOutsideWindow(receipt, now)) reasons.push(OverrideReason.OutsideWindow);
  if (lines.some((line) => line.policyFee > 0 && line.fee === 0)) reasons.push(OverrideReason.FeeWaived);
  if (lines.some((line) => line.item.final_sale)) reasons.push(OverrideReason.FinalSale);
  return reasons;
}

/** Condition choices for a receipt, from its policy. */
export function conditionOptions(policy: ReturnPolicy): { value: ReturnCondition; label: string }[] {
  return policyConditions(policy).map((condition) => ({ value: condition.key, label: condition.label }));
}

const BASE_REASONS: { key: string; label: string }[] = [
  { key: "changed_mind", label: "Changed mind" },
  { key: "defective", label: "Defective" },
  { key: "wrong_item", label: "Wrong item" },
  { key: "damaged_in_transit", label: "Damaged in transit" },
  { key: "not_as_described", label: "Not as described" },
  { key: "other", label: "Other" },
];

/** Reason choices for a receipt, from its policy. */
export function reasonOptions(policy: ReturnPolicy): { value: ReturnReason; label: string }[] {
  return (policy.reasons?.length ? policy.reasons : BASE_REASONS).map((reason) => ({ value: reason.key, label: reason.label }));
}

/** The default condition: the first that goes back on the shelf. */
export function defaultCondition(policy: ReturnPolicy): ReturnCondition {
  const rules = policyConditions(policy);
  return (rules.find((condition) => condition.restock) ?? rules[0])?.key ?? "unopened_resealable";
}

/** The default reason: "changed mind" when the policy has it, else its first reason. */
export function defaultReason(policy: ReturnPolicy): ReturnReason {
  const options = reasonOptions(policy);
  return options.find((option) => option.value === "changed_mind")?.value ?? options[0]?.value ?? "other";
}

/** A condition that sends the unit to repair counts as faulty (the reason becomes "defective"). */
export function isFaultyCondition(policy: ReturnPolicy, key: ReturnCondition): boolean {
  return conditionRule(policy, key)?.serial_status === "repair";
}

export function conditionLabel(policy: ReturnPolicy, key: ReturnCondition): string {
  return conditionRule(policy, key)?.label ?? key.replace(/_/g, " ");
}

export function reasonLabel(policy: ReturnPolicy, key: ReturnReason): string {
  return reasonOptions(policy).find((option) => option.value === key)?.label ?? key.replace(/_/g, " ");
}

export const refundMethodLabels: Record<RefundMethod, string> = {
  cash: "Cash",
  original_card: "Card reversal",
  original_bnpl: "Pay-later refund",
  store_credit: "Store credit",
};

export const paymentLabels: Record<Receipt["payment_method"], string> = {
  cash: "Cash",
  card: "Card",
  transfer: "Bank transfer",
  store_credit: "Store credit",
  on_account: "On account",
  cheque: "Cheque",
  deposit: "Layaway deposit",
  qr: "QR payment",
  loyalty: "Loyalty points",
  trade_in: "Trade-in credit",
  channel: "Delivery app",
  bnpl: "Pay later",
  gift_card: "Gift card",
};

/** Where the returned unit goes, matching how the API updates serial status and stock. */
export function restockInstruction(line: PricedLine, policy: ReturnPolicy): string {
  const rule = conditionRule(policy, line.draft.condition);
  if (!line.item.is_serialized) return rule?.restock ? "Back to shelf" : "Set aside, not restocked";
  const status = rule?.serial_status ?? policy.serial_status_by_condition[line.draft.condition];
  if (status === "in_stock") return "Back to shelf";
  if (status === "repair") return "Send to repairs";
  return "Open-box quarantine";
}

export const overrideLabels: Record<OverrideReason, string> = {
  no_refund_permission: "Cashier cannot issue refunds",
  outside_window: "Sale is outside the return and exchange windows",
  fee_waived: "Restocking fee waived",
  final_sale: "A final-sale item is returned",
};

/** Mirrors ALLOWED_TENDERS in the API: cash never goes back for a card sale; the exchange window gives a voucher. */
export function allowedRefundMethods(payment: Receipt["payment_method"], exchangeOnly = false): RefundMethod[] {
  if (exchangeOnly) return [RefundMethod.StoreCredit];
  if (payment === PaymentMethod.Cash) return [RefundMethod.Cash, RefundMethod.StoreCredit];
  if (payment === PaymentMethod.Card) return [RefundMethod.OriginalCard, RefundMethod.StoreCredit];
  if (payment === PaymentMethod.Bnpl) return [RefundMethod.OriginalBnpl, RefundMethod.StoreCredit];
  return [RefundMethod.StoreCredit];
}

export function storeCreditCode(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  const chars = Array.from(bytes, (byte) => CREDIT_ALPHABET[byte % CREDIT_ALPHABET.length]).join("");
  return `SC-${chars.slice(0, 4)}-${chars.slice(4, 8)}-${chars.slice(8, 12)}`;
}

export interface ReturnDraft {
  receipt: Receipt;
  lines: PricedLine[];
  tenders: { method: RefundMethod; amount: number }[];
  cashierId: string;
  notes: string;
  approval: { approverId: string; reasons: OverrideReason[]; note: string } | null;
  /** This register's offline credit-note number; null lets the API number it. */
  creditNoteNumber?: string | null;
  shiftId?: string | null;
}

export function buildReturnEvent(draft: ReturnDraft, creditCode: string): SyncEvent {
  const totals = returnTotals(draft.lines);
  const processedAt = new Date().toISOString();
  const payload: ReturnUpsert = {
    id: crypto.randomUUID(),
    original_sale_id: draft.receipt.sale_id,
    store_id: draft.receipt.store_id,
    cashier_id: draft.cashierId,
    currency: draft.receipt.currency,
    processed_at: processedAt,
    subtotal_cents: totals.subtotal,
    tax_refund_cents: totals.tax,
    restocking_fee_cents: totals.fee,
    total_refund_cents: totals.total,
    reason_notes: draft.notes.trim(),
    credit_note_number: draft.creditNoteNumber ?? null,
    shift_id: draft.shiftId ?? null,
    items: draft.lines.map((line) => ({
      id: crypto.randomUUID(),
      sale_item_id: line.item.sale_item_id,
      product_id: line.item.product_id,
      quantity: line.draft.quantity,
      unit_price_cents: line.item.unit_price_cents,
      tax_refund_cents: line.tax,
      restocking_fee_cents: line.fee,
      refund_cents: line.refund,
      condition_status: line.draft.condition,
      reason_code: line.draft.reason,
      serial_value: line.item.is_serialized ? line.draft.serialValue : null,
      serial_kind: line.item.is_serialized ? line.draft.serialKind : null,
    })),
    tenders: draft.tenders
      .filter((tender) => tender.amount > 0)
      .map((tender) => ({
        method: tender.method,
        amount_cents: tender.amount,
        store_credit_code: tender.method === RefundMethod.StoreCredit ? creditCode : null,
      })),
    override:
      draft.approval === null
        ? null
        : { approved_by_id: draft.approval.approverId, reasons: draft.approval.reasons, note: draft.approval.note },
  };
  return {
    idempotency_key: crypto.randomUUID(),
    entity_type: SyncEntityType.SaleReturn,
    operation: SyncOperation.Upsert,
    payload: { ...payload },
    occurred_at: processedAt,
  };
}
