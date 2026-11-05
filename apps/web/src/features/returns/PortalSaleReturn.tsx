import {
  Permission,
  RefundMethod,
  discountShareCents,
  formatMoney,
  hasPermission,
  policyConditions,
  proratedTaxCents,
  restockingFeeCents,
  weighedLineCents,
  type Receipt,
  type ReceiptItem,
  type RefundMethod as RefundMethodValue,
  type User,
} from "@ai-pos/shared-types";
import { useEffect, useMemo, useState } from "react";
import { GhostButton, PrimaryButton } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";

const DAY_MS = 86_400_000;

const METHOD_LABEL: Record<string, string> = {
  cash: "Cash",
  original_card: "Original card",
  original_bnpl: "Pay later",
  store_credit: "Store credit",
};

const ALLOWED: Record<string, RefundMethodValue[]> = {
  cash: [RefundMethod.Cash, RefundMethod.StoreCredit],
  card: [RefundMethod.OriginalCard, RefundMethod.StoreCredit],
  transfer: [RefundMethod.StoreCredit],
  store_credit: [RefundMethod.StoreCredit],
  gift_card: [RefundMethod.StoreCredit],
  bnpl: [RefundMethod.OriginalBnpl, RefundMethod.StoreCredit],
};

interface LineDraft {
  quantity: number;
  condition: string;
  reason: string;
  serial: string;
}

function remaining(item: ReceiptItem): number {
  return Math.max(0, item.quantity - item.returned_quantity);
}

function creditCode(): string {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const bytes = crypto.getRandomValues(new Uint8Array(12));
  const chars = Array.from(bytes, (byte) => alphabet[byte % alphabet.length]).join("");
  return `SC-${chars.slice(0, 4)}-${chars.slice(4, 8)}-${chars.slice(8, 12)}`;
}

function priceLine(item: ReceiptItem, draft: LineDraft, feeBps: number) {
  const gross = item.sold_by_weight
    ? weighedLineCents(draft.quantity, item.unit_price_cents)
    : item.unit_price_cents * draft.quantity;
  const subtotal =
    gross - discountShareCents(item.discount_cents ?? 0, item.quantity, draft.quantity, item.returned_quantity);
  const tax = proratedTaxCents(
    item.tax_cents,
    item.quantity,
    draft.quantity,
    item.returned_quantity,
    item.refunded_tax_cents,
  );
  const fee = item.sold_by_weight
    ? restockingFeeCents(gross, 1, feeBps)
    : restockingFeeCents(item.unit_price_cents, draft.quantity, feeBps);
  return { subtotal, tax, fee, refund: subtotal + tax - fee };
}

export function PortalSaleReturn({
  user,
  invoice,
  onClose,
  onReturned,
}: {
  user: User;
  invoice: string;
  onClose: () => void;
  onReturned: () => void;
}) {
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [drafts, setDrafts] = useState<Record<string, LineDraft>>({});
  const [method, setMethod] = useState<RefundMethodValue>(RefundMethod.Cash);
  const [notes, setNotes] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    apiGet<Receipt>(`/api/v1/returns/receipts/${encodeURIComponent(invoice)}`)
      .then((body) => {
        if (controller.signal.aborted) return;
        const conditions = policyConditions(body.policy);
        const condition = (conditions.find((row) => row.restock) ?? conditions[0])?.key ?? "unopened_resealable";
        const reasons = body.policy.reasons?.length
          ? body.policy.reasons
          : [{ key: "changed_mind", label: "Changed mind" }];
        const reason = reasons.find((row) => row.key === "changed_mind")?.key ?? reasons[0]?.key ?? "other";
        const next: Record<string, LineDraft> = {};
        for (const item of body.items) {
          const left = remaining(item);
          next[item.sale_item_id] = {
            quantity: item.gift_card || item.final_sale ? 0 : left > 0 ? 1 : 0,
            condition,
            reason,
            serial: "",
          };
        }
        setReceipt(body);
        setDrafts(next);
        const age = (Date.now() - new Date(body.created_at).getTime()) / DAY_MS;
        const exchangeOnly =
          age > body.policy.window_days && age <= body.policy.window_days + (body.policy.exchange_window_days ?? 0);
        const allowed = exchangeOnly ? [RefundMethod.StoreCredit] : (ALLOWED[body.payment_method] ?? [RefundMethod.StoreCredit]);
        setMethod(allowed[0] ?? RefundMethod.StoreCredit);
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(caught instanceof ApiRequestError ? caught.message : "The receipt could not be opened.");
        }
      });
    return () => controller.abort();
  }, [invoice]);

  const priced = useMemo(() => {
    if (receipt === null) return [];
    const rules = policyConditions(receipt.policy);
    return receipt.items.flatMap((item) => {
      const draft = drafts[item.sale_item_id];
      if (draft === undefined || draft.quantity < 1) return [];
      const feeBps = rules.find((row) => row.key === draft.condition)?.fee_bps ?? 0;
      return [{ item, draft, ...priceLine(item, draft, feeBps) }];
    });
  }, [drafts, receipt]);

  const totals = priced.reduce(
    (sum, line) => ({
      subtotal: sum.subtotal + line.subtotal,
      tax: sum.tax + line.tax,
      fee: sum.fee + line.fee,
      total: sum.total + line.refund,
    }),
    { subtotal: 0, tax: 0, fee: 0, total: 0 },
  );

  const ageDays = receipt === null ? 0 : (Date.now() - new Date(receipt.created_at).getTime()) / DAY_MS;
  const pastWindow =
    receipt !== null && ageDays > receipt.policy.window_days + (receipt.policy.exchange_window_days ?? 0);
  const exchangeOnly =
    receipt !== null &&
    ageDays > receipt.policy.window_days &&
    ageDays <= receipt.policy.window_days + (receipt.policy.exchange_window_days ?? 0);
  const methods = exchangeOnly ? [RefundMethod.StoreCredit] : receipt === null ? [] : (ALLOWED[receipt.payment_method] ?? [RefundMethod.StoreCredit]);
  const canRefund = hasPermission(user, Permission.PosRefund);
  const blocked =
    !canRefund
      ? "Your account cannot issue refunds."
      : pastWindow
        ? "This sale is outside the return window. Approve it on the register."
        : priced.some((line) => line.item.final_sale)
          ? "A final-sale item has to be approved on the register."
          : priced.some((line) => line.item.is_serialized && line.draft.serial.trim().length < 4)
            ? "Enter the serial or IMEI for each returned unit."
            : null;

  const submit = async () => {
    if (receipt === null || priced.length === 0 || blocked !== null || busy) return;
    setBusy(true);
    setError(null);
    const code = method === RefundMethod.StoreCredit ? creditCode() : null;
    try {
      const result = await apiPost<{ credit_note_number: string | null }>("/api/v1/returns", {
        id: crypto.randomUUID(),
        original_sale_id: receipt.sale_id,
        store_id: receipt.store_id,
        cashier_id: user.id,
        currency: receipt.currency,
        processed_at: new Date().toISOString(),
        subtotal_cents: totals.subtotal,
        tax_refund_cents: totals.tax,
        restocking_fee_cents: totals.fee,
        total_refund_cents: totals.total,
        reason_notes: notes.trim(),
        credit_note_number: null,
        shift_id: null,
        items: priced.map((line) => ({
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
          serial_value: line.item.is_serialized ? line.draft.serial.trim() : null,
          serial_kind: line.item.is_serialized ? line.item.serial_kind : null,
        })),
        tenders: [{ method, amount_cents: totals.total, store_credit_code: code }],
        override: null,
      }, { "Idempotency-Key": crypto.randomUUID() });
      setDone(result.credit_note_number ?? "Return recorded");
      onReturned();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "The return could not be saved.");
    } finally {
      setBusy(false);
    }
  };

  const money = (cents: number) => formatMoney(cents, receipt?.currency ?? "USD");
  const conditions = receipt === null ? [] : policyConditions(receipt.policy);
  const reasons = receipt?.policy.reasons?.length
    ? receipt.policy.reasons
    : [
        { key: "changed_mind", label: "Changed mind" },
        { key: "defective", label: "Defective" },
        { key: "wrong_item", label: "Wrong item" },
        { key: "other", label: "Other" },
      ];

  return (
    <Modal
      title={done ? "Return recorded" : `Return ${invoice}`}
      subtitle={done ? done : "Refund the items from this receipt. Stock and the credit note follow the same rules as the register."}
      onClose={onClose}
      width="lg"
      footer={
        done ? (
          <PrimaryButton onClick={onClose}>Done</PrimaryButton>
        ) : (
          <>
            <GhostButton onClick={onClose}>Cancel</GhostButton>
            <PrimaryButton loading={busy} loadingText="Saving return..." disabled={receipt === null || priced.length === 0 || blocked !== null} onClick={() => void submit()}>
              Refund {money(totals.total)}
            </PrimaryButton>
          </>
        )
      }
    >
      {error ? <p className="mb-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-700">{error}</p> : null}
      {blocked && !done ? <p className="mb-3 text-sm text-charcoal/70">{blocked}</p> : null}
      {receipt === null && error === null ? <p className="text-sm text-charcoal/60">Opening the receipt…</p> : null}
      {receipt && !done ? (
        <div className="space-y-4">
          {exchangeOnly ? <p className="text-sm text-charcoal/70">This sale is past the refund window, so the refund is store credit.</p> : null}
          <ul className="space-y-3">
            {receipt.items.map((item) => {
              const draft = drafts[item.sale_item_id];
              const left = remaining(item);
              if (draft === undefined) return null;
              return (
                <li key={item.sale_item_id} className="rounded-2xl border border-line p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{item.name}</p>
                      <p className="text-xs text-charcoal/60">{item.sku} · {left} left to return · {money(item.unit_price_cents)}</p>
                    </div>
                    <label className="text-xs font-medium text-charcoal/70">
                      Qty
                      <input
                        type="number"
                        min={0}
                        max={left}
                        disabled={left === 0 || item.gift_card === true || item.final_sale === true}
                        value={draft.quantity}
                        onChange={(event) => {
                          const quantity = Math.min(left, Math.max(0, Number(event.target.value) || 0));
                          setDrafts((current) => ({ ...current, [item.sale_item_id]: { ...draft, quantity } }));
                        }}
                        className="mt-1 h-[38px] w-20 rounded-xl border border-line px-2 text-sm"
                      />
                    </label>
                  </div>
                  {item.gift_card ? <p className="mt-2 text-xs text-charcoal/60">Void the gift card instead of returning this line.</p> : null}
                  {item.final_sale ? <p className="mt-2 text-xs text-charcoal/60">Final sale. Approve this line on the register.</p> : null}
                  {draft.quantity > 0 ? (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <label className="text-xs font-medium text-charcoal/70">
                        Condition
                        <select
                          className="mt-1 h-[38px] w-full rounded-xl border border-line px-2 text-sm"
                          value={draft.condition}
                          onChange={(event) => setDrafts((current) => ({ ...current, [item.sale_item_id]: { ...draft, condition: event.target.value } }))}
                        >
                          {conditions.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}
                        </select>
                      </label>
                      <label className="text-xs font-medium text-charcoal/70">
                        Reason
                        <select
                          className="mt-1 h-[38px] w-full rounded-xl border border-line px-2 text-sm"
                          value={draft.reason}
                          onChange={(event) => setDrafts((current) => ({ ...current, [item.sale_item_id]: { ...draft, reason: event.target.value } }))}
                        >
                          {reasons.map((row) => <option key={row.key} value={row.key}>{row.label}</option>)}
                        </select>
                      </label>
                      {item.is_serialized ? (
                        <label className="text-xs font-medium text-charcoal/70 sm:col-span-2">
                          Serial / IMEI{item.serial_last4 ? ` ending ${item.serial_last4}` : ""}
                          <input
                            className="mt-1 h-[38px] w-full rounded-xl border border-line px-3 text-sm"
                            value={draft.serial}
                            onChange={(event) => setDrafts((current) => ({ ...current, [item.sale_item_id]: { ...draft, serial: event.target.value } }))}
                          />
                        </label>
                      ) : null}
                    </div>
                  ) : null}
                </li>
              );
            })}
          </ul>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-xs font-medium text-charcoal/70">
              Refund to
              <select className="mt-1 h-[38px] w-full rounded-xl border border-line px-2 text-sm" value={method} onChange={(event) => setMethod(event.target.value as RefundMethodValue)}>
                {methods.map((item) => <option key={item} value={item}>{METHOD_LABEL[item] ?? item}</option>)}
              </select>
            </label>
            <label className="text-xs font-medium text-charcoal/70">
              Note
              <input className="mt-1 h-[38px] w-full rounded-xl border border-line px-3 text-sm" value={notes} onChange={(event) => setNotes(event.target.value)} />
            </label>
          </div>
          <p className="text-sm">Refund {money(totals.total)}{totals.fee > 0 ? ` after a ${money(totals.fee)} restocking fee` : ""}.</p>
        </div>
      ) : null}
    </Modal>
  );
}
