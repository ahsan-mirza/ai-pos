import { formatMoney, type PaymentIntent, type PaymentsConfig } from "@ai-pos/shared-types";
import { CheckCircle2, CreditCard, Loader2, ShieldCheck, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { ManagerApprovalModal } from "../../components/ManagerApprovalModal";
import type { CashierProfile } from "../../lib/tauri";
import { cancelPayment, pollPayment, simulatePayment, startCardPayment } from "./integratedPay";
import type { PaymentDraft, ProviderIntentDraft } from "./tenders";

const POLL_MS = 1500;

export function intentDraft(intent: PaymentIntent): ProviderIntentDraft {
  const card = intent.card_last4 ? `${intent.card_brand ?? "Card"} •••• ${intent.card_last4}` : null;
  return {
    id: intent.id,
    amountCents: intent.amount_cents,
    status: intent.status,
    provider: intent.provider,
    simulated: intent.simulated,
    customerUrl: intent.customer_url,
    authCode: intent.auth_code,
    cardLabel: card && intent.auth_code ? `${card} auth ${intent.auth_code}` : card,
    failure: intent.failure_reason,
  };
}

interface CardTerminalTenderProps {
  draft: PaymentDraft;
  totalCents: number;
  currency: string;
  disabled: boolean;
  config: PaymentsConfig;
  onChange: (draft: PaymentDraft) => void;
  verifyManager?: (username: string, pin: string) => Promise<CashierProfile>;
}

/** Sends the amount to the store's card terminal and waits for the approval; a manager can allow a manual entry. */
export function CardTerminalTender({ draft, totalCents, currency, disabled, config, onChange, verifyManager }: CardTerminalTenderProps) {
  const intent = draft.cardIntent ?? null;
  const manual = draft.cardManual ?? null;
  const [terminalId, setTerminalId] = useState<string | null>(config.default_terminal_id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [askManual, setAskManual] = useState(false);
  const terminal = config.terminals.find((row) => row.id === terminalId);
  const open = intent !== null && (intent.status === "PENDING" || intent.status === "AUTHORIZED");

  useEffect(() => {
    if (!intent || !open) return;
    const timer = window.setInterval(() => {
      void pollPayment(intent.id)
        .then((next) => {
          if (next.status !== intent.status) onChange({ ...draft, cardIntent: intentDraft(next) });
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [draft, intent, open, onChange]);

  const run = async (action: () => Promise<PaymentIntent>) => {
    setBusy(true);
    setError(null);
    try {
      onChange({ ...draft, cardIntent: intentDraft(await action()), cardManual: null });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (intent) await cancelPayment(intent.id).catch(() => undefined);
    onChange({ ...draft, cardIntent: null });
  };

  const stale = intent !== null && intent.amountCents !== totalCents;
  const closed = intent === null || stale || ["DECLINED", "EXPIRED", "CANCELLED"].includes(intent.status);

  if (manual) {
    return (
      <div className="flex items-center gap-2 rounded-2xl border border-zinc-200 bg-white/[0.03] p-3 text-sm dark:border-zinc-800">
        <ShieldCheck size={16} className="shrink-0 text-primary" aria-hidden="true" />
        <span className="min-w-0 flex-1">
          Manual card entry approved by <span className="font-semibold">{manual.approverName}</span>. Take the card on the standalone machine.
        </span>
        <button type="button" onClick={() => onChange({ ...draft, cardManual: null })} className="text-xs font-semibold text-primary">
          Undo
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-2 rounded-2xl border border-zinc-200 bg-white/[0.03] p-3 dark:border-zinc-800">
      {closed ? (
        <>
          {config.terminals.length > 1 ? (
            <div className="flex flex-wrap gap-1" role="group" aria-label="Card terminal">
              {config.terminals.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  aria-pressed={row.id === terminalId}
                  onClick={() => setTerminalId(row.id)}
                  className={`h-7 rounded-full px-3 text-xs font-semibold ${
                    row.id === terminalId ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "bg-zinc-100 text-zinc-600 dark:bg-white/10 dark:text-white/70"
                  }`}
                >
                  {row.label}
                </button>
              ))}
            </div>
          ) : null}
          <button
            type="button"
            disabled={disabled || busy || totalCents <= 0}
            onClick={() => void run(() => startCardPayment(totalCents, terminalId))}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-zinc-900 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
          >
            {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <CreditCard size={16} aria-hidden="true" />}
            Send {formatMoney(totalCents, currency)} to {terminal?.label ?? "the card terminal"}
          </button>
          {intent?.status === "DECLINED" && !stale ? (
            <p role="alert" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
              <XCircle size={13} aria-hidden="true" /> {intent.failure ?? "The card was declined."} Try again or use another method.
            </p>
          ) : null}
          {stale ? <p className="text-xs text-zinc-600 dark:text-white/60">The total changed. Send the new amount.</p> : null}
          {intent?.status === "EXPIRED" ? <p className="text-xs text-zinc-600 dark:text-white/60">The terminal timed out. Send it again.</p> : null}
          {verifyManager ? (
            <button type="button" disabled={disabled} onClick={() => setAskManual(true)} className="text-xs font-semibold text-primary disabled:opacity-40">
              Terminal not responding? Manual card entry
            </button>
          ) : null}
        </>
      ) : intent.status === "PAID" ? (
        <p className="flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 size={18} className="text-primary" aria-hidden="true" />
          <span className="min-w-0 flex-1">
            Approved{intent.cardLabel ? ` · ${intent.cardLabel}` : ""}. Charge to finish.
          </span>
        </p>
      ) : (
        <div className="flex items-center gap-3">
          <Loader2 size={18} className="shrink-0 animate-spin text-primary" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Tap, insert or swipe on {terminal?.label ?? "the terminal"}</p>
            <p className="text-xs tabular-nums text-zinc-600 dark:text-white/60">{formatMoney(intent.amountCents, currency)}</p>
          </div>
          <button
            type="button"
            aria-label="Cancel card payment"
            onClick={() => void cancel()}
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}
      {open && intent?.simulated && config.simulator_controls ? (
        <div className="flex gap-2" role="group" aria-label="Simulated terminal">
          <button type="button" disabled={busy} onClick={() => void run(() => simulatePayment(intent.id, "approve"))}
            className="h-9 flex-1 rounded-xl bg-emerald-600 text-xs font-semibold text-white disabled:opacity-40">
            Simulate approval
          </button>
          <button type="button" disabled={busy} onClick={() => void run(() => simulatePayment(intent.id, "decline"))}
            className="h-9 flex-1 rounded-xl bg-zinc-100 text-xs font-semibold text-zinc-700 disabled:opacity-40 dark:bg-white/10 dark:text-white/80">
            Simulate decline
          </button>
        </div>
      ) : null}
      {error ? <p role="alert" className="text-xs text-red-600 dark:text-red-400">{error}</p> : null}
      {askManual && verifyManager ? (
        <ManagerApprovalModal
          reasons={[`Card payment of ${formatMoney(totalCents, currency)} taken without the integrated terminal`]}
          subtitle="A manager who approves overrides must enter their PIN."
          verify={verifyManager}
          approveLabel="Allow manual entry"
          onClose={() => setAskManual(false)}
          onApproved={(approver, note) => {
            onChange({
              ...draft,
              cardIntent: null,
              cardManual: { approvedById: approver.id, approverName: approver.full_name, note: note || "Terminal unavailable" },
            });
            setAskManual(false);
          }}
        />
      ) : null}
    </div>
  );
}
