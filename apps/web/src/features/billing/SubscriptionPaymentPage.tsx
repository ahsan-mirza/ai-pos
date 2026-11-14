import { formatMoney } from "@ai-pos/shared-types";
import { AxizDatePicker, formatDate, useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { invalidateAccountSubscription } from "../../components/layout/AccountMenu";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { ApiRequestError, apiBlob, apiGet, apiUpload } from "../../lib/api";
import { SubscriptionCenter, type SubscriptionSummary } from "./SubscriptionCenter";

interface PaymentAttention {
  kind: "awaiting_proof" | "pending_review" | "rejected" | "revoked";
  invoice_id: string;
  plan_code: string;
  cycle_code: string;
  currency: string;
  total_fils: number;
  issued_at: string;
  bank: Record<string, string> | null;
  transfer_id: string | null;
  reason: string | null;
}

interface AccessStatus {
  state: string;
  ai_allowed: boolean;
  operational?: boolean;
  attention: PaymentAttention | null;
  subscription?: SubscriptionSummary | null;
  promotional_trial?: {
    eligible: boolean;
    status: string;
    capabilities?: string[];
    days_remaining?: number | null;
    expires_at?: string | null;
  } | null;
}

const ATTENTION_STATUS: Record<PaymentAttention["kind"], string> = {
  awaiting_proof: "Awaiting payment",
  pending_review: "Under verification",
  rejected: "Payment rejected",
  revoked: "Subscription access was updated",
};

function attentionLabel(kind: PaymentAttention["kind"]): string {
  return ATTENTION_STATUS[kind];
}

const copy: Record<PaymentAttention["kind"], { title: string; message: string }> = {
  awaiting_proof: {
    title: "Payment Required",
    message:
      "Your invoice is ready. Transfer the amount shown on your invoice and submit your payment proof. Your subscription features will remain locked until payment is verified.",
  },
  pending_review: {
    title: "Payment Verification Pending",
    message:
      "We have received your payment proof. Our team will review it and update your subscription status. Your paid features will remain locked until verification and activation are complete.",
  },
  rejected: {
    title: "Payment Proof Needs Attention",
    message: "Send a corrected proof for this invoice. Features stay locked until the payment is verified.",
  },
  revoked: {
    title: "Subscription access was updated",
    message: "The previous activation was revoked. Paid features stay locked until a payment is verified again.",
  },
};

export function SubscriptionPaymentPage() {
  const { t } = useLocale();
  const [access, setAccess] = useState<AccessStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [date, setDate] = useState("");
  const [reference, setReference] = useState("");
  const [bank, setBank] = useState("");
  const [note, setNote] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID());

  const load = () => {
    apiGet<AccessStatus>("/api/v1/billing/access")
      .then((found) => {
        setAccess(found);
        setError(null);
      })
      .catch((caught: unknown) => setError(caught instanceof ApiRequestError ? caught.message : "Could not load the invoice."));
  };

  useEffect(() => {
    load();
  }, []);

  const attention = access?.attention ?? null;

  const submit = async () => {
    if (attention === null || file === null || date === "") return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const form = new FormData();
      form.set("invoice_id", attention.invoice_id);
      form.set("amount_fils", String(attention.total_fils));
      form.set("transferred_on", date);
      form.set("idempotency_key", idempotencyKey);
      form.set("bank_reference", reference);
      form.set("sending_bank", bank);
      form.set("note", note);
      form.set("receipt", file);
      await apiUpload("/api/v1/billing/transfers", form);
      invalidateAccountSubscription();
      setNotice("Payment proof submitted. Features stay locked until it is verified.");
      setIdempotencyKey(crypto.randomUUID());
      setFile(null);
      load();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not submit the payment proof.");
    } finally {
      setBusy(false);
    }
  };

  const openProof = async () => {
    if (attention?.transfer_id == null) return;
    try {
      const blob = await apiBlob(`/api/v1/billing/transfers/${attention.transfer_id}/receipt`);
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank", "noopener,noreferrer");
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not open the submitted proof.");
    }
  };

  if (access === null && error === null) {
    return (
      <section className="grid gap-4" aria-busy="true">
        <div className="h-16 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
        <div className="h-40 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <div key={index} className="h-56 animate-pulse rounded-3xl bg-zinc-100 dark:bg-zinc-800" />
          ))}
        </div>
      </section>
    );
  }

  const trial = access?.promotional_trial;
  const proof =
    attention === null ? null : (
      <PaymentProof
        attention={attention}
        notice={notice}
        error={error}
        busy={busy}
        date={date}
        reference={reference}
        bank={bank}
        note={note}
        file={file}
        onDate={setDate}
        onReference={setReference}
        onBank={setBank}
        onNote={setNote}
        onFile={setFile}
        onSubmit={() => void submit()}
        onOpenProof={() => void openProof()}
      />
    );

  return (
    <SubscriptionCenter
      subscription={access?.subscription ?? null}
      attention={
        attention
          ? {
              kind: attention.kind,
              invoice_id: attention.invoice_id,
              plan_code: attention.plan_code,
              cycle_code: attention.cycle_code,
              currency: attention.currency,
              total_fils: attention.total_fils,
            }
          : null
      }
      trialEligible={trial?.eligible === true && trial.status === "not_started"}
      accessState={access?.state ?? null}
      trial={
        trial
          ? {
              status: trial.status,
              capabilities: trial.capabilities ?? [],
              days_remaining: trial.days_remaining ?? null,
              expires_at: trial.expires_at ?? null,
            }
          : null
      }
      onInvoiced={load}
      billing={
        <>
          <ErrorNote message={attention || !error ? null : t(error)} />
          {proof}
        </>
      }
    />
  );
}

function PaymentProof({
  attention,
  notice,
  error,
  busy,
  date,
  reference,
  bank,
  note,
  file,
  onDate,
  onReference,
  onBank,
  onNote,
  onFile,
  onSubmit,
  onOpenProof,
}: {
  attention: PaymentAttention;
  notice: string | null;
  error: string | null;
  busy: boolean;
  date: string;
  reference: string;
  bank: string;
  note: string;
  file: File | null;
  onDate: (value: string) => void;
  onReference: (value: string) => void;
  onBank: (value: string) => void;
  onNote: (value: string) => void;
  onFile: (value: File | null) => void;
  onSubmit: () => void;
  onOpenProof: () => void;
}) {
  const { t } = useLocale();
  const text = copy[attention.kind];
  const details = attention.bank;
  const canSubmit = attention.kind === "awaiting_proof" || attention.kind === "rejected";

  return (
    <div className="grid gap-4">
      <header>
        <h3 className="text-lg font-semibold tracking-tight text-charcoal dark:text-white">{t(text.title)}</h3>
        <p className="mt-2 text-sm text-charcoal/70 dark:text-white/70">{attention.kind === "rejected" && attention.reason ? attention.reason : t(text.message)}</p>
      </header>
      {notice ? <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm font-medium text-charcoal dark:text-white">{t(notice)}</p> : null}
      <ErrorNote message={error ? t(error) : null} />
      <article className="rounded-2xl border border-line bg-zinc-50 p-5 dark:bg-white/5">
        <h2 className="text-lg font-semibold text-charcoal dark:text-white">{t("Invoice")}</h2>
        <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-charcoal/50">{t("Invoice")}</dt>
            <dd className="font-mono font-medium" dir="ltr">{attention.invoice_id.slice(0, 8)}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">{t("Status")}</dt>
            <dd className="font-medium">{t(attentionLabel(attention.kind))}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">{t("Plan")}</dt>
            <dd className="font-medium" dir="ltr">{attention.plan_code}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">{t("Duration")}</dt>
            <dd className="font-medium" dir="ltr">{attention.cycle_code}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">{t("Amount due")}</dt>
            <dd className="font-medium" dir="ltr">{formatMoney(attention.total_fils, attention.currency)}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">{t("Issued")}</dt>
            <dd className="font-medium tabular-nums" dir="ltr">{formatDate(attention.issued_at) || attention.issued_at.slice(0, 10)}</dd>
          </div>
        </dl>
        {details ? (
          <dl className="mt-4 grid gap-1 border-t border-line pt-4 text-sm">
            <div>
              <dt className="inline text-charcoal/50">{t("Account name")} </dt>
              <dd className="inline">{details.holder_name}</dd>
            </div>
            <div>
              <dt className="inline text-charcoal/50">{t("Bank")} </dt>
              <dd className="inline">{details.bank_name}</dd>
            </div>
            {details.iban ? (
              <div>
                <dt className="inline text-charcoal/50">{t("IBAN")} </dt>
                <dd className="inline font-mono" dir="ltr">{details.iban}</dd>
              </div>
            ) : null}
            {details.account_number ? (
              <div>
                <dt className="inline text-charcoal/50">{t("Account number")} </dt>
                <dd className="inline font-mono" dir="ltr">{details.account_number}</dd>
              </div>
            ) : null}
            {details.swift ? (
              <div>
                <dt className="inline text-charcoal/50">{t("SWIFT")} </dt>
                <dd className="inline font-mono" dir="ltr">{details.swift}</dd>
              </div>
            ) : null}
            <p className="text-charcoal/60">
              {[details.country, details.currency].filter(Boolean).join(" · ")}
              {details.instructions ? ` · ${details.instructions}` : ""}
            </p>
          </dl>
        ) : (
          <p className="mt-4 text-sm text-charcoal/60">{t("This invoice has no bank instructions copied onto it.")}</p>
        )}
      </article>

      {attention.transfer_id && attention.kind !== "awaiting_proof" ? (
        <button type="button" onClick={onOpenProof} className="text-start text-sm font-semibold text-accent">
          {t("View submitted proof")}
        </button>
      ) : null}

      {canSubmit ? (
        <form
          className="grid gap-3 rounded-2xl border border-line bg-white p-5 dark:bg-zinc-900"
          onSubmit={(event) => {
            event.preventDefault();
            onSubmit();
          }}
        >
          <h2 className="text-lg font-semibold text-charcoal dark:text-white">{attention.kind === "rejected" ? t("Resubmit payment proof") : t("Submit payment proof")}</h2>
          <p className="text-sm text-charcoal/60 dark:text-white/60">
            {t("The amount is the invoice total. A different amount is not accepted. Uploading proof does not activate the subscription.")}
          </p>
          <label className="grid gap-1 text-sm">
            {t("Payment date")}
            <AxizDatePicker required leading aria-label={t("Payment date")} value={date} onChange={(event) => onDate(event.target.value)} className="h-10 w-full rounded-xl border border-line bg-white text-sm dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
          </label>
          <label className="grid gap-1 text-sm">
            {t("Transfer reference")}
            <input value={reference} onChange={(event) => onReference(event.target.value)} className="h-10 rounded-xl border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" dir="ltr" />
          </label>
          <label className="grid gap-1 text-sm">
            {t("Sending bank")}
            <input value={bank} onChange={(event) => onBank(event.target.value)} className="h-10 rounded-xl border border-line bg-white px-3 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
          </label>
          <label className="grid gap-1 text-sm">
            {t("Note")}
            <textarea value={note} onChange={(event) => onNote(event.target.value)} className="min-h-20 rounded-xl border border-line bg-white px-3 py-2 dark:border-zinc-700 dark:bg-zinc-950 dark:text-white" />
          </label>
          <label className="grid gap-1 text-sm">
            {t("Transaction slip (PNG, JPEG, or PDF, up to 2 MB)")}
            <input
              type="file"
              required
              accept="image/png,image/jpeg,application/pdf"
              onChange={(event) => onFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div>
            <PrimaryButton type="submit" disabled={busy || file === null || date === ""}>
              {busy ? t("Submitting…") : t("Submit payment proof")}
            </PrimaryButton>
          </div>
        </form>
      ) : null}
    </div>
  );
}
