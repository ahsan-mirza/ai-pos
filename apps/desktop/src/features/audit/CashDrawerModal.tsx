import { formatMoney } from "@ai-pos/shared-types";
import { Banknote, CheckCircle2, Clock, Inbox, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import {
  auditStatus,
  inTauri,
  openCashDrawer,
  recentAuditEvents,
  recordCashMovement,
  type AuditQueueStatus,
  type LocalAuditEvent,
} from "../../lib/tauri";
import { activeShiftId } from "../shifts/shift";
import { recordRegisterEvent } from "./registerAudit";

type Mode = "no_sale" | "cash_drop";

const reasons: Record<Mode, string[]> = {
  no_sale: ["Give change", "Swap notes for coins", "Count check", "Other"],
  cash_drop: ["Drawer over limit", "Shift change", "Safe deposit", "Other"],
};

interface CashDrawerModalProps {
  currency: string;
  onClose: () => void;
  onLogged: (message: string) => void;
}

export function CashDrawerModal({ currency, onClose, onLogged }: CashDrawerModalProps) {
  const titleId = useId();
  const [mode, setMode] = useState<Mode>("no_sale");
  const [reason, setReason] = useState(reasons.no_sale[0]!);
  const [note, setNote] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<LocalAuditEvent[]>([]);
  const [queue, setQueue] = useState<AuditQueueStatus | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  useEffect(() => {
    if (!inTauri()) return;
    void recentAuditEvents(30)
      .then((rows) => setRecent(rows.filter((row) => row.action_type === "DRAWER_OPEN" || row.action_type === "CASH_DROP").slice(0, 4)))
      .catch(() => undefined);
    void auditStatus().then(setQueue).catch(() => undefined);
  }, []);

  const switchMode = (next: Mode) => {
    setMode(next);
    setReason(reasons[next][0]!);
    setError(null);
  };

  const cents = Math.round(Number.parseFloat(amount.replace(/,/g, "")) * 100);
  const amountValid = Number.isFinite(cents) && cents > 0 && cents <= 100_000_000;
  const explanation = reason === "Other" ? note.trim() : [reason, note.trim()].filter(Boolean).join(" · ");
  const canSubmit = !busy && explanation.length >= 3 && (mode === "no_sale" || amountValid);

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      if (mode === "no_sale") {
        await recordRegisterEvent({
          action_type: "DRAWER_OPEN",
          action: "drawer.no_sale",
          target_entity: "CashDrawer",
          reason_notes: explanation,
          details: { kind: "no_sale" },
        });
        if (activeShiftId()) {
          await recordCashMovement({
            id: crypto.randomUUID(),
            kind: "NO_SALE",
            amount_cents: 0,
            reason: explanation,
            occurred_at: new Date().toISOString(),
          });
        }
        const kicked = inTauri() ? await openCashDrawer().then(() => null, (failure: unknown) => String(failure)) : null;
        onLogged(kicked ? `Logged to the audit trail, but the drawer did not open: ${kicked}` : "Drawer opened. Logged to the audit trail.");
      } else {
        await recordRegisterEvent({
          action_type: "CASH_DROP",
          action: "drawer.cash_drop",
          target_entity: "CashDrawer",
          reason_notes: explanation,
          new_values: { amount_cents: cents, currency },
          details: { amount_cents: cents, reference: reference.trim() || null },
        });
        if (activeShiftId()) {
          await recordCashMovement({
            id: crypto.randomUUID(),
            kind: "CASH_DROP",
            amount_cents: cents,
            reason: [explanation, reference.trim()].filter(Boolean).join(" · "),
            occurred_at: new Date().toISOString(),
          });
        }
        onLogged(`Cash drop of ${formatMoney(cents, currency)} logged to the audit trail.`);
      }
      onClose();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-lg">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Inbox size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Cash drawer
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">Every open and drop is recorded with your name and the reason.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <div className="mt-5 grid grid-cols-2 gap-1 rounded-full bg-charcoal p-1" role="tablist" aria-label="Drawer action">
          {(
            [
              ["no_sale", "Open drawer (no sale)"],
              ["cash_drop", "Cash drop"],
            ] as const
          ).map(([value, label]) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={mode === value}
              onClick={() => switchMode(value)}
              className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                mode === value ? "bg-primary text-white" : "text-white/70 hover:text-white"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {mode === "cash_drop" ? (
            <div className="grid grid-cols-[1fr_150px] gap-3">
              <label className="text-sm font-medium" htmlFor="drop-amount">
                Amount removed ({currency})
                <input
                  id="drop-amount"
                  autoFocus
                  inputMode="decimal"
                  autoComplete="off"
                  value={amount}
                  onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
                  placeholder="0.00"
                  className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
                />
              </label>
              <label className="text-sm font-medium" htmlFor="drop-reference">
                Bag / envelope
                <input
                  id="drop-reference"
                  autoComplete="off"
                  maxLength={40}
                  value={reference}
                  onChange={(event) => setReference(event.target.value)}
                  placeholder="Optional"
                  className="modal-input mt-1.5 font-normal"
                />
              </label>
            </div>
          ) : null}

          <fieldset>
            <legend className="text-sm font-medium">Reason</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {reasons[mode].map((item) => (
                <button
                  key={item}
                  type="button"
                  aria-pressed={reason === item}
                  onClick={() => setReason(item)}
                  className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                    reason === item ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-surface dark:bg-zinc-800/60 text-charcoal dark:text-zinc-100 hover:bg-charcoal/10 dark:hover:bg-white/10"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </fieldset>

          <label className="block text-sm font-medium" htmlFor="drawer-note">
            {reason === "Other" ? "Explain why" : "Note"}
            <textarea
              id="drawer-note"
              value={note}
              maxLength={250}
              rows={2}
              onChange={(event) => setNote(event.target.value)}
              placeholder={reason === "Other" ? "Required" : "Optional"}
              className="modal-input mt-1.5 resize-none text-sm font-normal"
            />
          </label>

          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}

          {recent.length > 0 ? (
            <div className="rounded-2xl bg-surface dark:bg-zinc-800/60 p-3">
              <p className="px-1 text-[11px] font-semibold uppercase tracking-wider text-charcoal/50 dark:text-zinc-400">Recent on this register</p>
              <ul className="mt-2 space-y-1.5">
                {recent.map((row) => {
                  const dropped = (row.details?.amount_cents as number | undefined) ?? null;
                  return (
                    <li key={row.id} className="flex items-center gap-2 text-xs">
                      <Banknote size={13} className="shrink-0 text-charcoal/50 dark:text-zinc-400" aria-hidden="true" />
                      <span className="min-w-0 flex-1 truncate">
                        <span className="font-semibold">{row.action_type === "CASH_DROP" ? "Cash drop" : "No sale"}</span>
                        {" · "}
                        {row.user_name} · {row.reason_notes}
                        {dropped !== null ? ` · ${formatMoney(dropped, currency)}` : ""}
                      </span>
                      <span className="shrink-0 tabular-nums text-charcoal/50 dark:text-zinc-400">
                        {new Date(row.occurred_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                      </span>
                      {row.status === "synced" ? (
                        <CheckCircle2 size={13} className="shrink-0 text-charcoal dark:text-zinc-100" aria-label="Synced" />
                      ) : (
                        <Clock size={13} className="shrink-0 text-primary" aria-label="Waiting to sync" />
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-3 pt-2">
            <p className="text-xs tabular-nums text-charcoal/50 dark:text-zinc-400">
              {queue && queue.pending > 0 ? `${queue.pending} audit event${queue.pending === 1 ? "" : "s"} waiting to sync` : ""}
            </p>
            <div className="flex gap-3">
              <button type="button" onClick={onClose} disabled={busy} className="modal-cancel">
                Cancel
              </button>
              <button type="submit" disabled={!canSubmit} className="modal-save">
                {busy ? "Logging…" : mode === "no_sale" ? "Open drawer" : "Record drop"}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
