import { formatMoney, type CollectionMethod, type Customer, type OpenInvoice, type PaymentResult } from "@ai-pos/shared-types";
import { useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { centsText, customersApi, message, toCents } from "./api";

const methods = [
  { value: "transfer", label: "Bank transfer" },
  { value: "cheque", label: "Cheque / PDC" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
] as const;

type Method = CollectionMethod | "cheque";

const today = () => new Date().toISOString().slice(0, 10);

interface ReceivePaymentModalProps {
  customer: Customer;
  invoices: OpenInvoice[];
  currency: string;
  onClose: () => void;
  onReceived: (result: PaymentResult) => void;
}

export function ReceivePaymentModal({ customer, invoices, currency, onClose, onReceived }: ReceivePaymentModalProps) {
  const [amount, setAmount] = useState(centsText(Math.max(0, customer.current_balance_cents)));
  const [method, setMethod] = useState<Method>("transfer");
  const [reference, setReference] = useState("");
  const [bank, setBank] = useState("");
  const [chequeDate, setChequeDate] = useState(today());
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cents = toCents(amount);

  /** Oldest invoice first, exactly as the API allocates it. */
  const preview = useMemo(() => {
    let remaining = cents ?? 0;
    const rows: { invoice: OpenInvoice; applied: number }[] = [];
    for (const invoice of invoices) {
      if (remaining <= 0) break;
      const applied = Math.min(remaining, invoice.due_balance_cents);
      rows.push({ invoice, applied });
      remaining -= applied;
    }
    return { rows, unapplied: remaining };
  }, [cents, invoices]);

  const save = async () => {
    if (cents === null || cents <= 0) {
      setError("Enter the amount received.");
      return;
    }
    if (method === "transfer" && reference.trim() === "") {
      setError("Enter the transfer reference.");
      return;
    }
    if (method === "cheque" && (reference.trim() === "" || bank.trim() === "" || chequeDate === "")) {
      setError("Enter the cheque number, bank and the date on the cheque.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onReceived(
        await customersApi.receivePayment(customer.id, {
          amount_cents: cents,
          method,
          reference: reference.trim(),
          note: note.trim(),
          cheque:
            method === "cheque"
              ? { cheque_number: reference.trim(), bank: bank.trim(), cheque_date: chequeDate }
              : null,
        }),
      );
    } catch (caught) {
      setError(message(caught, "Could not record the payment."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title="Receive payment"
      subtitle={`${customer.company_name ?? customer.name} owes ${formatMoney(customer.current_balance_cents, currency)}`}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Recording…" : `Record ${cents !== null ? formatMoney(cents, currency) : "payment"}`}
          </PrimaryButton>
        </>
      }
    >
      <SegmentedControl label="Payment method" value={method} options={methods} onChange={setMethod} />
      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <TextField
          label={`Amount received (${currency})`}
          inputMode="decimal"
          value={amount}
          className="text-lg font-semibold tabular-nums"
          onChange={(event) => setAmount(event.target.value)}
        />
        <TextField
          label={
            method === "transfer" ? "Transfer reference" : method === "cheque" ? "Cheque number" : "Receipt reference (optional)"
          }
          value={reference}
          maxLength={method === "cheque" ? 32 : 120}
          onChange={(event) => setReference(event.target.value)}
        />
        {method === "cheque" ? (
          <>
            <TextField label="Bank" value={bank} maxLength={80} onChange={(event) => setBank(event.target.value)} />
            <TextField
              label="Date on the cheque"
              type="date"
              value={chequeDate}
              hint={chequeDate > today() ? "Post-dated: tracked on the Cheques page until it clears." : undefined}
              onChange={(event) => setChequeDate(event.target.value)}
            />
          </>
        ) : null}
      </div>
      <div className="mt-4">
        <TextField label="Note (optional)" value={note} maxLength={255} onChange={(event) => setNote(event.target.value)} />
      </div>
      <div className="mt-5 rounded-2xl bg-surface p-4">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">Applied oldest invoice first</p>
        {preview.rows.length === 0 ? (
          <p className="mt-2 text-sm text-charcoal/60">No open invoices. The payment stays on account as credit.</p>
        ) : (
          <ul className="mt-2 space-y-1.5 text-sm">
            {preview.rows.map(({ invoice, applied }) => (
              <li key={invoice.sale_id} className="flex items-center justify-between gap-3">
                <span>
                  <span className="font-mono text-xs">{invoice.invoice}</span>
                  {invoice.days_overdue > 0 ? (
                    <span className="ml-2 rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold text-white">
                      {invoice.days_overdue}d overdue
                    </span>
                  ) : null}
                </span>
                <span className="tabular-nums">
                  {formatMoney(applied, currency)}
                  <span className="text-charcoal/40"> / {formatMoney(invoice.due_balance_cents, currency)}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
        {preview.unapplied > 0 && preview.rows.length > 0 ? (
          <p className="mt-2 text-xs text-charcoal/60">
            {formatMoney(preview.unapplied, currency)} stays on the account as credit.
          </p>
        ) : null}
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}
