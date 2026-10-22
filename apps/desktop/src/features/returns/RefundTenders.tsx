import { RefundMethod, formatMoney, type Receipt } from "@ai-pos/shared-types";
import { Banknote, CalendarClock, CreditCard, Gift, type LucideIcon } from "lucide-react";
import { paymentLabels, refundMethodLabels } from "./returnMath";

const tenderMeta: Record<RefundMethod, { icon: LucideIcon; help: string }> = {
  cash: { icon: Banknote, help: "Paid out from the drawer." },
  original_card: { icon: CreditCard, help: "Reversed to the card used on the sale." },
  original_bnpl: { icon: CalendarClock, help: "Refunded through Tabby or Tamara; the customer's plan shrinks." },
  store_credit: { icon: Gift, help: "Issued as a store credit code." },
};

interface RefundTendersProps {
  receipt: Receipt;
  allowed: RefundMethod[];
  amounts: Record<RefundMethod, string>;
  total: number;
  disabled: boolean;
  onChange: (method: RefundMethod, value: string) => void;
  onFill: (method: RefundMethod) => void;
}

export function RefundTenders({ receipt, allowed, amounts, total, disabled, onChange, onFill }: RefundTendersProps) {
  return (
    <div className="grid gap-3 md:grid-cols-3">
      {Object.values(RefundMethod)
        .filter((method) => method !== RefundMethod.OriginalBnpl || allowed.includes(method))
        .map((method) => {
        const { icon: Icon, help } = tenderMeta[method];
        const enabled = allowed.includes(method);
        const inputId = `tender-${method}`;
        const blocked =
          method === RefundMethod.Cash
            ? `Not for ${paymentLabels[receipt.payment_method].toLowerCase()} sales.`
            : method === RefundMethod.OriginalCard
              ? "Only for card sales."
              : null;
        return (
          <div
            key={method}
            className={`flex flex-col rounded-2xl border p-4 ${
              enabled ? "border-line dark:border-zinc-800 bg-surface dark:bg-zinc-800/60" : "border-dashed border-line dark:border-zinc-800 bg-white dark:bg-zinc-900 opacity-60"
            }`}
          >
            <div className="flex items-center gap-3">
              <span
                className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                  enabled ? "bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900" : "bg-surface dark:bg-zinc-800/60 text-charcoal/40 dark:text-zinc-500"
                }`}
              >
                <Icon size={18} aria-hidden="true" />
              </span>
              <div>
                <label htmlFor={inputId} className="block font-semibold">
                  {refundMethodLabels[method]}
                </label>
                <p className="text-xs text-charcoal/50 dark:text-zinc-400">{enabled ? help : blocked}</p>
              </div>
            </div>
            {method === RefundMethod.OriginalCard && enabled ? (
              <p className="mt-3 text-xs text-charcoal/60 dark:text-zinc-400 tabular-nums">
                {formatMoney(receipt.card_refundable_cents, receipt.currency)} left on the original card payment
              </p>
            ) : null}
            <div className="mt-auto flex items-end gap-2 pt-4">
              <input
                id={inputId}
                inputMode="decimal"
                placeholder="0.00"
                disabled={!enabled || disabled}
                value={amounts[method]}
                onChange={(event) => onChange(method, event.target.value)}
                className="h-11 min-w-0 flex-1 rounded-xl border border-line dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 text-base tabular-nums"
              />
              <button
                type="button"
                disabled={!enabled || disabled || total === 0}
                onClick={() => onFill(method)}
                className="h-11 rounded-xl bg-white dark:bg-zinc-900 px-3 text-sm font-medium ring-1 ring-line dark:ring-zinc-700 disabled:opacity-40"
              >
                Rest
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
