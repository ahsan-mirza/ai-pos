import { formatMoney, type PaymentIntent, type PaymentsConfig } from "@ai-pos/shared-types";
import { CalendarClock, CheckCircle2, Loader2, X, XCircle } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import type { RegisterCustomer } from "../../lib/tauri";
import { intentDraft } from "./CardTerminalTender";
import { cancelPayment, pollPayment, simulatePayment, startBnplPayment } from "./integratedPay";
import type { PaymentDraft } from "./tenders";

const POLL_MS = 2000;
const PHONE = /^\+?[0-9 ]{7,20}$/;

interface BnplTenderProps {
  draft: PaymentDraft;
  totalCents: number;
  currency: string;
  disabled: boolean;
  config: PaymentsConfig;
  customer: RegisterCustomer | null;
  onChange: (draft: PaymentDraft) => void;
}

const inputClass =
  "h-10 w-full rounded-xl border border-zinc-200 bg-white px-3 text-sm text-zinc-900 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-white";

/** Tabby or Tamara: the customer opens the provider's checkout on their phone (QR here and on the customer display). */
export function BnplTender({ draft, totalCents, currency, disabled, config, customer, onChange }: BnplTenderProps) {
  const intent = draft.bnplIntent ?? null;
  const [provider, setProvider] = useState(config.bnpl[0]?.name ?? "");
  const [phone, setPhone] = useState(customer?.phone ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const open = intent !== null && (intent.status === "PENDING" || intent.status === "AUTHORIZED");
  const label = config.bnpl.find((row) => row.name === (intent?.provider ?? provider))?.label ?? "Pay later";

  useEffect(() => {
    if (!intent?.customerUrl || !open) {
      setImage(null);
      return;
    }
    void QRCode.toDataURL(intent.customerUrl, { margin: 1, width: 220, color: { dark: "#222026", light: "#FFFFFF" } }).then(setImage);
  }, [intent?.customerUrl, open]);

  useEffect(() => {
    if (!intent || !open) return;
    const timer = window.setInterval(() => {
      void pollPayment(intent.id)
        .then((next) => {
          if (next.status !== intent.status) onChange({ ...draft, bnplIntent: intentDraft(next) });
        })
        .catch(() => undefined);
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [draft, intent, open, onChange]);

  const run = async (action: () => Promise<PaymentIntent>) => {
    setBusy(true);
    setError(null);
    try {
      onChange({ ...draft, bnplIntent: intentDraft(await action()) });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const start = () =>
    run(() =>
      startBnplPayment({
        amountCents: totalCents,
        provider,
        phone: phone.trim(),
        name: customer?.company_name ?? customer?.name ?? "",
        email: customer?.email ?? "",
        items: [{ name: "In-store purchase", quantity: 1, unit_cents: totalCents }],
      }),
    );

  const cancel = async () => {
    if (intent) await cancelPayment(intent.id).catch(() => undefined);
    onChange({ ...draft, bnplIntent: null });
  };

  if (config.bnpl.length === 0) {
    return <p className="rounded-2xl border border-zinc-200 p-3 text-xs text-zinc-600 dark:border-zinc-800 dark:text-white/60">No pay-later provider is set up.</p>;
  }
  const stale = intent !== null && intent.amountCents !== totalCents;
  const closed = intent === null || stale || ["DECLINED", "EXPIRED", "CANCELLED"].includes(intent.status);

  return (
    <div className="space-y-2 rounded-2xl border border-zinc-200 bg-white/[0.03] p-3 dark:border-zinc-800">
      {closed ? (
        <>
          <div className="flex flex-wrap gap-1" role="group" aria-label="Pay-later provider">
            {config.bnpl.map((row) => (
              <button
                key={row.name}
                type="button"
                aria-pressed={row.name === provider}
                onClick={() => setProvider(row.name)}
                className={`h-8 rounded-full px-3 text-xs font-semibold ${
                  row.name === provider ? "bg-zinc-900 text-white dark:bg-white dark:text-zinc-900" : "bg-zinc-100 text-zinc-600 dark:bg-white/10 dark:text-white/70"
                }`}
              >
                {row.label}
                {row.simulated && row.name !== "simulator" ? " (simulated)" : ""}
              </button>
            ))}
          </div>
          <label className="block text-xs font-medium text-zinc-600 dark:text-white/60" htmlFor="bnpl-phone">
            Customer's mobile number
            <input id="bnpl-phone" inputMode="tel" value={phone} onChange={(event) => setPhone(event.target.value)}
              placeholder="+971 50 123 4567" className={`${inputClass} mt-1`} />
          </label>
          <button
            type="button"
            disabled={disabled || busy || totalCents <= 0 || !PHONE.test(phone.trim()) || provider === ""}
            onClick={() => void start()}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-zinc-900 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
          >
            {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <CalendarClock size={16} aria-hidden="true" />}
            Start {label} checkout for {formatMoney(totalCents, currency)}
          </button>
          {intent?.status === "DECLINED" && !stale ? (
            <p role="alert" className="flex items-center gap-1.5 text-xs text-red-600 dark:text-red-400">
              <XCircle size={13} aria-hidden="true" /> {intent.failure ?? "The plan was not approved."} Offer another method.
            </p>
          ) : null}
          {stale ? <p className="text-xs text-zinc-600 dark:text-white/60">The total changed. Start a new checkout.</p> : null}
        </>
      ) : intent.status === "PAID" ? (
        <p className="flex items-center gap-2 text-sm font-semibold">
          <CheckCircle2 size={18} className="text-primary" aria-hidden="true" />
          {label} plan approved and captured. Charge to finish.
        </p>
      ) : (
        <div className="flex items-center gap-3">
          <div className="flex h-28 w-28 shrink-0 items-center justify-center rounded-xl bg-white p-1.5 ring-1 ring-zinc-200 dark:ring-0">
            {image ? <img src={image} alt={`${label} checkout QR code`} className="h-full w-full" /> : <Loader2 size={20} className="animate-spin" aria-hidden="true" />}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">Customer scans to finish on {label}</p>
            <p className="mt-0.5 text-xs tabular-nums text-zinc-600 dark:text-white/60">{formatMoney(intent.amountCents, currency)}</p>
            <p className="mt-2 flex items-center gap-1.5 text-xs text-zinc-600 dark:text-white/60">
              <Loader2 size={12} className="animate-spin" aria-hidden="true" />
              {intent.status === "AUTHORIZED" ? "Approved, capturing…" : "Waiting for the customer…"}
            </p>
          </div>
          <button type="button" aria-label="Cancel pay-later checkout" onClick={() => void cancel()}
            className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white">
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      )}
      {open && intent?.simulated && config.simulator_controls ? (
        <div className="flex gap-2" role="group" aria-label="Simulated provider">
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
    </div>
  );
}
