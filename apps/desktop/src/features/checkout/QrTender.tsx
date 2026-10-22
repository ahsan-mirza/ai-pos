import { formatMoney } from "@ai-pos/shared-types";
import { CheckCircle2, Loader2, QrCode, X } from "lucide-react";
import QRCode from "qrcode";
import { useEffect, useState } from "react";
import { cancelIntent, createIntent, getIntent } from "./qrPay";
import type { PaymentDraft } from "./tenders";

interface QrTenderProps {
  draft: PaymentDraft;
  totalCents: number;
  currency: string;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
}

/** Shows the payment QR (here and on the customer display) and polls until the provider confirms payment. */
export function QrTender({ draft, totalCents, currency, disabled, onChange }: QrTenderProps) {
  const intent = draft.qrIntent ?? null;
  const [image, setImage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!intent) {
      setImage(null);
      return;
    }
    void QRCode.toDataURL(intent.payload, { margin: 1, width: 220, color: { dark: "#222026", light: "#FFFFFF" } }).then(setImage);
  }, [intent]);

  useEffect(() => {
    if (!intent || intent.status !== "PENDING") return;
    const timer = window.setInterval(() => {
      void getIntent(intent.id)
        .then((next) => {
          if (next.status !== intent.status) onChange({ ...draft, qrIntent: { ...intent, status: next.status } });
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(timer);
  }, [draft, intent, onChange]);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await createIntent(totalCents);
      onChange({
        ...draft,
        qrIntent: { id: created.id, amountCents: created.amount_cents, payload: created.qr_payload, status: created.status },
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (intent) await cancelIntent(intent.id).catch(() => undefined);
    onChange({ ...draft, qrIntent: null });
  };

  const stale = intent !== null && intent.amountCents !== totalCents;

  return (
    <div className="rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white/[0.03] p-3">
      {intent === null || stale || intent.status === "EXPIRED" || intent.status === "CANCELLED" ? (
        <>
          <button
            type="button"
            disabled={disabled || busy || totalCents <= 0}
            onClick={() => void start()}
            className="flex h-12 w-full items-center justify-center gap-2 rounded-xl bg-zinc-900 text-sm font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
          >
            {busy ? <Loader2 size={16} className="animate-spin" aria-hidden="true" /> : <QrCode size={16} aria-hidden="true" />}
            Show QR for {formatMoney(totalCents, currency)}
          </button>
          {stale ? <p className="mt-2 text-xs text-zinc-600 dark:text-white/60">The total changed. Show a new QR.</p> : null}
          {intent?.status === "EXPIRED" ? <p className="mt-2 text-xs text-zinc-600 dark:text-white/60">The QR expired. Show a new one.</p> : null}
        </>
      ) : (
        <div className="flex items-center gap-3">
          <div className="flex h-28 w-28 shrink-0 items-center justify-center rounded-xl bg-white p-1.5 ring-1 ring-zinc-200 dark:ring-0">
            {intent.status === "PAID" ? (
              <CheckCircle2 size={56} className="text-primary" aria-hidden="true" />
            ) : image ? (
              <img src={image} alt="Payment QR code" className="h-full w-full" />
            ) : null}
          </div>
          <div className="min-w-0 flex-1">
            <p className="text-sm font-semibold">{intent.status === "PAID" ? "Paid. Charge to finish." : "Customer scans to pay"}</p>
            <p className="mt-0.5 text-xs text-zinc-600 dark:text-white/60 tabular-nums">{formatMoney(intent.amountCents, currency)}</p>
            {intent.status === "PENDING" ? (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-zinc-600 dark:text-white/60">
                <Loader2 size={12} className="animate-spin" aria-hidden="true" /> Waiting for confirmation…
              </p>
            ) : null}
          </div>
          {intent.status === "PENDING" ? (
            <button
              type="button"
              aria-label="Cancel QR payment"
              onClick={() => void cancel()}
              className="flex h-9 w-9 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
            >
              <X size={16} aria-hidden="true" />
            </button>
          ) : null}
        </div>
      )}
      {error ? <p role="alert" className="mt-2 text-xs text-red-600 dark:text-red-400">{error}</p> : null}
    </div>
  );
}
