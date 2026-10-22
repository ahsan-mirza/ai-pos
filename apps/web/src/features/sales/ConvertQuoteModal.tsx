import { formatMoney, type PaymentMethod, type Quote, type TenderInput } from "@ai-pos/shared-types";
import { useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { centsText, message, toCents } from "../customers/api";
import { quotesApi } from "./api";

type Choice = "transfer" | "cash" | "card" | "on_account";
type DepositMethod = "transfer" | "cash" | "card";

const choices = [
  { value: "transfer", label: "Transfer / Cheque" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "on_account", label: "On Account" },
] as const;

const depositMethods = [
  { value: "transfer", label: "Transfer" },
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
] as const;

interface ConvertQuoteModalProps {
  quote: Quote;
  currency: string;
  onClose: () => void;
  onConverted: (quote: Quote) => void;
}

export function ConvertQuoteModal({ quote, currency, onClose, onConverted }: ConvertQuoteModalProps) {
  const onAccountAllowed = quote.customer_id !== null && quote.sale_type === "WHOLESALE";
  const [choice, setChoice] = useState<Choice>(onAccountAllowed ? "on_account" : "transfer");
  const [deposit, setDeposit] = useState("0.00");
  const [depositMethod, setDepositMethod] = useState<DepositMethod>("transfer");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const deposited = quote.deposits_cents ?? 0;
  /** Layaway deposits are applied by the server; only the balance is collected here. */
  const total = quote.total_cents - deposited;
  const depositCents = toCents(deposit);

  const plan = (): { method: PaymentMethod; tenders?: TenderInput[] } | string => {
    if (total <= 0) return { method: "cash" };
    if (choice !== "on_account") {
      if (choice === "transfer" && reference.trim() === "") return "Enter the cheque or transfer reference.";
      return { method: choice, tenders: [{ method: choice, amount_cents: total, reference: reference.trim() }] };
    }
    if (depositCents === null || depositCents > total) return "The deposit must be between zero and the total.";
    if (depositCents > 0 && depositMethod === "transfer" && reference.trim() === "") {
      return "Enter the deposit's cheque or transfer reference.";
    }
    const tenders: TenderInput[] = [];
    if (depositCents > 0) {
      tenders.push({ method: depositMethod, amount_cents: depositCents, reference: depositMethod === "transfer" ? reference.trim() : "" });
    }
    if (total - depositCents > 0) tenders.push({ method: "on_account", amount_cents: total - depositCents });
    return { method: total - depositCents > 0 ? "on_account" : depositMethod, tenders };
  };

  const convert = async () => {
    const result = plan();
    if (typeof result === "string") {
      setError(result);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      onConverted(await quotesApi.convert(quote.id, { payment_method: result.method, tenders: result.tenders }));
    } catch (caught) {
      setError(message(caught, "Could not convert the quote."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Convert ${quote.number}`}
      subtitle={`${quote.customer_name ?? "Walk-in"} · ${formatMoney(quote.total_cents, currency)} at the quoted prices${
        deposited ? ` · ${formatMoney(deposited, currency)} already deposited` : ""
      }`}
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void convert()}>
            {busy ? "Converting…" : "Convert to sale"}
          </PrimaryButton>
        </>
      }
    >
      <SegmentedControl
        label="Payment"
        value={choice}
        options={onAccountAllowed ? choices : choices.filter((item) => item.value !== "on_account")}
        onChange={setChoice}
      />
      {choice === "on_account" ? (
        <div className="mt-5 grid gap-4 md:grid-cols-2">
          <TextField
            label={`Deposit received (${currency})`}
            inputMode="decimal"
            value={deposit}
            className="tabular-nums"
            onChange={(event) => setDeposit(event.target.value)}
          />
          <div>
            <p className="text-sm font-medium">Deposit method</p>
            <div className="mt-1.5">
              <SegmentedControl label="Deposit method" value={depositMethod} options={depositMethods} onChange={setDepositMethod} />
            </div>
          </div>
        </div>
      ) : null}
      {choice === "transfer" || (choice === "on_account" && (depositCents ?? 0) > 0 && depositMethod === "transfer") ? (
        <div className="mt-4">
          <TextField
            label="Cheque or transfer reference"
            value={reference}
            maxLength={64}
            onChange={(event) => setReference(event.target.value)}
          />
        </div>
      ) : null}
      <dl className="mt-5 grid gap-3 rounded-2xl bg-surface p-4 text-sm md:grid-cols-3">
        <div>
          <dt className="text-xs text-charcoal/50">Paid now</dt>
          <dd className="mt-1 font-semibold tabular-nums">
            {formatMoney(choice === "on_account" ? (depositCents ?? 0) : total, currency)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-charcoal/50">Balance on credit</dt>
          <dd className="mt-1 font-semibold tabular-nums text-accent">
            {formatMoney(choice === "on_account" ? Math.max(0, total - (depositCents ?? 0)) : 0, currency)}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-charcoal/50">{deposited ? "Balance due" : "Total"}</dt>
          <dd className="mt-1 font-semibold tabular-nums">{formatMoney(total, currency)}</dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-charcoal/60">
        Reserved stock is released into the sale. Phones quoted without IMEIs get free in-stock units assigned, oldest
        stock first.
      </p>
      {choice === "on_account" && deposit === centsText(total) ? (
        <p className="mt-2 text-xs text-charcoal/60">The full amount is paid, so nothing goes on account.</p>
      ) : null}
      <ErrorNote message={error} />
    </Modal>
  );
}
