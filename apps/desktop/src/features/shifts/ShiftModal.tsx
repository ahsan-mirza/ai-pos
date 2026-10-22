import { Permission, formatMoney } from "@ai-pos/shared-types";
import { Clock, X } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import {
  closeShift,
  nextDocumentNumber,
  recordCashMovement,
  shiftSummary,
  type ShiftSummary,
} from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { useBusinessCurrency } from "../checkout/currency";
import { parseAmount, setShift } from "./shift";

type Tab = "x" | "cash" | "close";

const methodLabels: Record<string, string> = {
  cash: "Cash",
  card: "Card",
  transfer: "Bank transfer",
  cheque: "Cheque",
  store_credit: "Store credit",
  original_card: "Card reversal",
  deposit: "Deposit",
  qr: "QR payment",
  loyalty: "Loyalty points",
  trade_in: "Trade-in credit",
  channel: "Delivery apps",
};

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className={`flex justify-between gap-3 py-1.5 text-sm ${strong ? "font-semibold" : ""}`}>
      <dt className={strong ? "" : "text-charcoal/60 dark:text-zinc-400"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

export function ShiftModal({ session, onClose }: { session: CashierSession; onClose: () => void }) {
  const titleId = useId();
  const currency = useBusinessCurrency();
  const money = (cents: number) => formatMoney(cents, currency);
  const canSeeExpected = session.user.permissions.includes(Permission.PosShiftManage);
  const [tab, setTab] = useState<Tab>("x");
  const [summary, setSummary] = useState<ShiftSummary | null>(null);
  const [kind, setKind] = useState<"PAY_IN" | "PAY_OUT">("PAY_OUT");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [counted, setCounted] = useState("");
  const [countedForeign, setCountedForeign] = useState<Record<string, string>>({});
  const [notes, setNotes] = useState("");
  const [closed, setClosed] = useState<ShiftSummary | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(() => {
    void shiftSummary()
      .then(setSummary)
      .catch((caught: unknown) => setError(String(caught)));
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy && closed === null) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, closed, onClose]);

  const run = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await work();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const moveCents = parseAmount(amount);
  const countedCents = parseAmount(counted);

  const submitMovement = () =>
    run(async () => {
      if (moveCents === null || moveCents <= 0) throw new Error("Enter the amount of cash moved.");
      await recordCashMovement({
        id: crypto.randomUUID(),
        kind,
        amount_cents: moveCents,
        reason: reason.trim(),
        occurred_at: new Date().toISOString(),
      });
      setNotice(`${kind === "PAY_IN" ? "Pay-in" : "Pay-out"} of ${money(moveCents)} recorded.`);
      setAmount("");
      setReason("");
      load();
    });

  const submitClose = () =>
    run(async () => {
      if (countedCents === null || counted.trim() === "") throw new Error("Count the drawer and enter the total.");
      const foreign: Record<string, number> = {};
      for (const code of Object.keys(summary?.foreign_cash ?? {})) {
        const value = parseAmount(countedForeign[code] ?? "");
        if (value === null || (countedForeign[code] ?? "").trim() === "") throw new Error(`Count the ${code} cash too.`);
        foreign[code] = value;
      }
      const zNumber = await nextDocumentNumber("Z").catch(() => null);
      setClosed(
        await closeShift({
          closed_at: new Date().toISOString(),
          counted_cash_cents: countedCents,
          z_number: zNumber,
          notes: notes.trim(),
          counted_foreign: foreign,
        }),
      );
    });

  const report = closed ?? summary;
  const variance = closed ? (closed.shift.counted_cash_cents ?? 0) - closed.expected_cash_cents : null;

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-xl">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Clock size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {closed ? `Shift closed${closed.shift.z_number ? ` · ${closed.shift.z_number}` : ""}` : "Shift"}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">
              {report
                ? `Opened by ${report.shift.opened_by_name} at ${new Date(report.shift.opened_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })} with ${money(report.shift.opening_float_cents)}`
                : "Loading…"}
            </p>
          </div>
          {closed === null ? (
            <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
              <X size={18} aria-hidden="true" />
            </button>
          ) : null}
        </div>

        {closed === null ? (
          <div className="mt-5 grid grid-cols-3 gap-1 rounded-full bg-charcoal p-1" role="tablist" aria-label="Shift actions">
            {(
              [
                ["x", "X report"],
                ["cash", "Pay in / out"],
                ["close", "Close shift"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                role="tab"
                aria-selected={tab === value}
                onClick={() => {
                  setTab(value);
                  setError(null);
                  setNotice(null);
                }}
                className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                  tab === value ? "bg-primary text-white" : "text-white/70 hover:text-white"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        ) : null}

        {(tab === "x" || closed) && report ? (
          <dl className="mt-5 divide-y divide-line dark:divide-zinc-800 rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-2">
            <Row label={`Sales (${report.sales_count})`} value={money(report.sales_total_cents)} strong />
            {Object.entries(report.tenders).map(([method, cents]) => (
              <Row key={method} label={`  ${methodLabels[method] ?? method}`} value={money(cents)} />
            ))}
            {report.tips_cents ? <Row label="Tips (owed to staff)" value={money(report.tips_cents)} /> : null}
            {report.returns_count > 0 ? (
              <Row
                label={`Refunds (${report.returns_count})`}
                value={`−${money(Object.values(report.refund_tenders).reduce((sum, cents) => sum + cents, 0))}`}
              />
            ) : null}
            {report.pay_in_cents > 0 ? <Row label="Pay-ins" value={money(report.pay_in_cents)} /> : null}
            {report.pay_out_cents > 0 ? <Row label="Pay-outs" value={`−${money(report.pay_out_cents)}`} /> : null}
            {report.drops_cents > 0 ? <Row label="Safe drops" value={`−${money(report.drops_cents)}`} /> : null}
            {report.no_sale_count > 0 ? <Row label="No-sale opens" value={String(report.no_sale_count)} /> : null}
            {Object.entries(report.foreign_cash ?? {}).map(([code, cents]) => (
              <Row
                key={code}
                label={`${code} cash drawer`}
                value={
                  closed
                    ? `${formatMoney(cents, code)} expected · ${formatMoney(parseAmount(countedForeign[code] ?? "0") ?? 0, code)} counted`
                    : canSeeExpected
                      ? formatMoney(cents, code)
                      : "Hidden until close"
                }
              />
            ))}
            {closed ? (
              <>
                <Row label="Expected in drawer" value={money(closed.expected_cash_cents)} strong />
                <Row label="Counted" value={money(closed.shift.counted_cash_cents ?? 0)} strong />
                <div className="flex justify-between py-2 text-base font-semibold">
                  <dt>{variance === 0 ? "Balanced" : variance !== null && variance > 0 ? "Over" : "Short"}</dt>
                  <dd className={`tabular-nums ${variance === 0 ? "" : "text-primary"}`}>{money(Math.abs(variance ?? 0))}</dd>
                </div>
              </>
            ) : (
              <Row
                label="Expected cash in drawer"
                value={canSeeExpected ? money(report.expected_cash_cents) : "Hidden until close"}
                strong
              />
            )}
          </dl>
        ) : null}

        {tab === "cash" && closed === null ? (
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submitMovement();
            }}
          >
            <div className="flex gap-2">
              {(
                [
                  ["PAY_OUT", "Pay out (petty cash)"],
                  ["PAY_IN", "Pay in (top up)"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={kind === value}
                  onClick={() => setKind(value)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    kind === value ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-surface dark:bg-zinc-800/60 text-charcoal dark:text-zinc-100 hover:bg-charcoal/10 dark:hover:bg-white/10"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <label className="block text-sm font-medium" htmlFor="move-amount">
              Amount ({currency})
              <input
                id="move-amount"
                inputMode="decimal"
                autoComplete="off"
                value={amount}
                onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
                placeholder="0.00"
                className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
              />
            </label>
            <label className="block text-sm font-medium" htmlFor="move-reason">
              Reason
              <input
                id="move-reason"
                maxLength={250}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
                placeholder="Courier, cleaning supplies, change from bank…"
                className="modal-input mt-1.5 font-normal"
              />
            </label>
            <div className="flex justify-end">
              <button type="submit" disabled={busy || reason.trim().length < 3} className="modal-save">
                {busy ? "Recording…" : "Record"}
              </button>
            </div>
          </form>
        ) : null}

        {tab === "close" && closed === null ? (
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              void submitClose();
            }}
          >
            <p className="rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-3 text-sm text-charcoal/70 dark:text-zinc-300">
              Count every note and coin in the drawer. The register shows what it expected only after you submit.
            </p>
            <label className="block text-sm font-medium" htmlFor="counted-cash">
              Counted cash ({currency})
              <input
                id="counted-cash"
                autoFocus
                inputMode="decimal"
                autoComplete="off"
                value={counted}
                onChange={(event) => setCounted(event.target.value.replace(/[^\d.,]/g, ""))}
                placeholder="0.00"
                className="modal-input mt-1.5 text-2xl font-semibold tabular-nums"
              />
            </label>
            {Object.keys(summary?.foreign_cash ?? {}).map((code) => (
              <label key={code} className="block text-sm font-medium" htmlFor={`counted-${code}`}>
                Counted {code} cash
                <input
                  id={`counted-${code}`}
                  inputMode="decimal"
                  autoComplete="off"
                  value={countedForeign[code] ?? ""}
                  onChange={(event) =>
                    setCountedForeign((current) => ({ ...current, [code]: event.target.value.replace(/[^\d.,]/g, "") }))
                  }
                  placeholder="0.00"
                  className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
                />
              </label>
            ))}
            <label className="block text-sm font-medium" htmlFor="close-notes">
              Note
              <textarea
                id="close-notes"
                rows={2}
                maxLength={500}
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Optional"
                className="modal-input mt-1.5 resize-none text-sm font-normal"
              />
            </label>
            <div className="flex justify-end">
              <button type="submit" disabled={busy || counted.trim() === ""} className="modal-save">
                {busy ? "Closing…" : "Close shift"}
              </button>
            </div>
          </form>
        ) : null}

        {error ? (
          <p role="alert" className="mt-4 text-sm font-medium text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p role="status" className="mt-4 text-sm font-medium">
            {notice}
          </p>
        ) : null}

        {closed ? (
          <div className="mt-5 flex justify-end">
            <button
              type="button"
              className="modal-save"
              onClick={() => {
                setShift(null);
                onClose();
              }}
            >
              Done
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
