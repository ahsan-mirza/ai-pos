import { formatMoney } from "@ai-pos/shared-types";
import { Loader2, TicketPercent, X } from "lucide-react";
import { useState } from "react";
import { lookupVoucher } from "./storeCredit";
import type { PaymentDraft } from "./tenders";

interface StoreCreditRowProps {
  draft: PaymentDraft;
  totalCents: number;
  currency: string;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
}

export function StoreCreditRow({ draft, totalCents, currency, disabled, onChange }: StoreCreditRowProps) {
  const [code, setCode] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const applied = draft.storeCredit ?? null;

  async function apply() {
    setChecking(true);
    setError(null);
    try {
      const voucher = await lookupVoucher(code);
      if (voucher.currency !== currency) {
        setError(`That voucher is in ${voucher.currency}; this register sells in ${currency}.`);
      } else if (voucher.balance_cents <= 0) {
        setError("That voucher has been fully used.");
      } else {
        onChange({ ...draft, storeCredit: { code: voucher.code, balanceCents: voucher.balance_cents } });
        setCode("");
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setChecking(false);
    }
  }

  if (applied !== null) {
    const used = Math.min(applied.balanceCents, totalCents);
    return (
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200 bg-white/[0.03] px-3 py-1.5 text-sm dark:border-zinc-800">
        <span className="flex min-w-0 items-center gap-2.5">
          <TicketPercent size={18} aria-hidden="true" className="shrink-0 text-primary" />
          <span className="min-w-0">
            <span className="block truncate font-semibold tabular-nums">{applied.code}</span>
            <span className="block text-xs text-zinc-600 tabular-nums dark:text-white/60">
              {formatMoney(used, currency)} used · {formatMoney(applied.balanceCents - used, currency)} left on the voucher
            </span>
          </span>
        </span>
        <button
          type="button"
          disabled={disabled}
          aria-label="Remove store credit"
          onClick={() => onChange({ ...draft, storeCredit: null })}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
        >
          <X size={16} aria-hidden="true" />
        </button>
      </div>
    );
  }

  const nothingDue = totalCents === 0;
  return (
    <div>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          void apply();
        }}
      >
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Store-credit voucher code</span>
          <TicketPercent size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            id="voucher-code"
            value={code}
            maxLength={24}
            disabled={disabled || nothingDue}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Store-credit voucher (SC-…)"
            className="h-10 w-full rounded-2xl border border-zinc-200 bg-white pl-9 pr-3 font-mono text-sm uppercase text-zinc-900 placeholder:font-sans placeholder:normal-case placeholder:text-zinc-400 focus:border-primary focus:outline-none focus:ring-4 focus:ring-primary/20 disabled:opacity-40 dark:border-zinc-800 dark:bg-zinc-900/60 dark:text-white dark:placeholder:text-white/30"
          />
        </label>
        <button
          type="submit"
          disabled={disabled || nothingDue || checking || code.trim() === ""}
          className="flex h-10 items-center gap-1.5 rounded-2xl bg-primary px-4 text-xs font-semibold text-white disabled:opacity-40"
        >
          {checking ? <Loader2 size={14} aria-hidden="true" className="animate-spin" /> : null}
          Apply
        </button>
      </form>
      {error ? (
        <p role="alert" className="mt-1 text-xs font-medium text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}
