import { formatMoney, type Quote } from "@ai-pos/shared-types";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { message, toCents } from "../customers/api";
import { quotesApi } from "./api";

type Method = "cash" | "card" | "transfer";

const methods = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "transfer", label: "Transfer" },
] as const;

export function TakeDepositModal({
  quote,
  currency,
  onClose,
  onSaved,
}: {
  quote: Quote;
  currency: string;
  onClose: () => void;
  onSaved: (quote: Quote) => void;
}) {
  const remaining = quote.total_cents - (quote.deposits_cents ?? 0);
  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<Method>("cash");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = async () => {
    const cents = toCents(amount);
    if (cents === null || cents <= 0 || cents > remaining) {
      setError(`Enter an amount up to ${formatMoney(remaining, currency)}.`);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onSaved(
        await quotesApi.addPayment(quote.id, { id: crypto.randomUUID(), amount_cents: cents, method, reference: reference.trim() }),
      );
    } catch (caught) {
      setError(message(caught, "Could not record the deposit."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Deposit on ${quote.number}`}
      subtitle={`${quote.customer_name ?? "Customer"} · ${formatMoney(remaining, currency)} left to pay`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Record deposit"}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        <TextField
          label={`Amount (${currency})`}
          inputMode="decimal"
          autoFocus
          value={amount}
          className="tabular-nums"
          onChange={(event) => setAmount(event.target.value)}
        />
        <SegmentedControl label="Method" value={method} options={methods} onChange={setMethod} />
        {method !== "cash" ? (
          <TextField label="Reference" maxLength={120} value={reference} onChange={(event) => setReference(event.target.value)} />
        ) : null}
        {(quote.payments ?? []).length > 0 ? (
          <ul className="divide-y divide-line rounded-2xl bg-surface px-4 text-sm">
            {(quote.payments ?? []).map((payment) => (
              <li key={payment.id} className="flex justify-between py-2">
                <span className="text-charcoal/70">
                  {new Date(payment.received_at).toLocaleDateString()} · {payment.method} · {payment.received_by_name ?? "—"}
                </span>
                <span className="font-semibold tabular-nums">{formatMoney(payment.amount_cents, currency)}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
