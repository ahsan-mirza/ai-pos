import { formatMoney } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { invalidateAccountSubscription } from "../../components/layout/AccountMenu";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { ApiRequestError, apiBlob, apiGet, apiUpload } from "../../lib/api";

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

  if (attention === null) {
    return (
      <section className="w-full">
        <h1 className="text-3xl font-semibold tracking-tight">Subscription payment</h1>
        <ErrorNote message={error} />
        <p className="mt-3 text-sm text-charcoal/60">
          {access === null ? "Loading the invoice…" : "There is no invoice waiting for a bank transfer."}
        </p>
      </section>
    );
  }

  const text = copy[attention.kind];
  const details = attention.bank;
  const canSubmit = attention.kind === "awaiting_proof" || attention.kind === "rejected";

  return (
    <section className="grid w-full gap-4">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">{text.title}</h1>
        <p className="mt-2 text-sm text-charcoal/70">{attention.kind === "rejected" && attention.reason ? attention.reason : text.message}</p>
      </header>
      {notice ? <p className="rounded-2xl bg-accent/10 px-4 py-3 text-sm font-medium">{notice}</p> : null}
      <ErrorNote message={error} />
      <article className="rounded-card border border-line bg-white p-6">
        <h2 className="text-lg font-semibold">Invoice</h2>
        <dl className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-charcoal/50">Invoice</dt>
            <dd className="font-mono font-medium">{attention.invoice_id.slice(0, 8)}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Status</dt>
            <dd className="font-medium">{attention.kind.replace(/_/g, " ")}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Plan</dt>
            <dd className="font-medium">{attention.plan_code}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Duration</dt>
            <dd className="font-medium">{attention.cycle_code}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Amount due</dt>
            <dd className="font-medium">{formatMoney(attention.total_fils, attention.currency)}</dd>
          </div>
          <div>
            <dt className="text-charcoal/50">Issued</dt>
            <dd className="font-medium">{attention.issued_at.slice(0, 10)}</dd>
          </div>
        </dl>
        {details ? (
          <dl className="mt-4 grid gap-1 border-t border-line pt-4 text-sm">
            <div>
              <dt className="inline text-charcoal/50">Account name </dt>
              <dd className="inline">{details.holder_name}</dd>
            </div>
            <div>
              <dt className="inline text-charcoal/50">Bank </dt>
              <dd className="inline">{details.bank_name}</dd>
            </div>
            {details.iban ? (
              <div>
                <dt className="inline text-charcoal/50">IBAN </dt>
                <dd className="inline font-mono">{details.iban}</dd>
              </div>
            ) : null}
            {details.account_number ? (
              <div>
                <dt className="inline text-charcoal/50">Account number </dt>
                <dd className="inline font-mono">{details.account_number}</dd>
              </div>
            ) : null}
            {details.swift ? (
              <div>
                <dt className="inline text-charcoal/50">SWIFT </dt>
                <dd className="inline font-mono">{details.swift}</dd>
              </div>
            ) : null}
            <p className="text-charcoal/60">
              {[details.country, details.currency].filter(Boolean).join(" · ")}
              {details.instructions ? ` · ${details.instructions}` : ""}
            </p>
          </dl>
        ) : (
          <p className="mt-4 text-sm text-charcoal/60">This invoice has no bank instructions copied onto it.</p>
        )}
      </article>

      {attention.transfer_id && attention.kind !== "awaiting_proof" ? (
        <button type="button" onClick={() => void openProof()} className="text-left text-sm font-semibold text-accent">
          View submitted proof
        </button>
      ) : null}

      {canSubmit ? (
        <form
          className="grid gap-3 rounded-card border border-line bg-white p-6"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <h2 className="text-lg font-semibold">{attention.kind === "rejected" ? "Resubmit payment proof" : "Submit payment proof"}</h2>
          <p className="text-sm text-charcoal/60">
            The amount is the invoice total. A different amount is not accepted. Uploading proof does not activate the subscription.
          </p>
          <label className="grid gap-1 text-sm">
            Payment date
            <input type="date" required value={date} onChange={(event) => setDate(event.target.value)} className="h-10 rounded-xl border border-line px-3" />
          </label>
          <label className="grid gap-1 text-sm">
            Transfer reference
            <input value={reference} onChange={(event) => setReference(event.target.value)} className="h-10 rounded-xl border border-line px-3" />
          </label>
          <label className="grid gap-1 text-sm">
            Sending bank
            <input value={bank} onChange={(event) => setBank(event.target.value)} className="h-10 rounded-xl border border-line px-3" />
          </label>
          <label className="grid gap-1 text-sm">
            Note
            <textarea value={note} onChange={(event) => setNote(event.target.value)} className="min-h-20 rounded-xl border border-line px-3 py-2" />
          </label>
          <label className="grid gap-1 text-sm">
            Transaction slip (PNG, JPEG, or PDF, up to 2 MB)
            <input
              type="file"
              required
              accept="image/png,image/jpeg,application/pdf"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <div>
            <PrimaryButton type="submit" disabled={busy || file === null || date === ""}>
              {busy ? "Submitting…" : "Submit payment proof"}
            </PrimaryButton>
          </div>
        </form>
      ) : null}
      <Link to="/" className="text-sm font-semibold text-accent">
        Back to the portal
      </Link>
    </section>
  );
}
