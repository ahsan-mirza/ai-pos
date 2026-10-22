import { formatMoney, GIFT_CARD_CODE } from "@ai-pos/shared-types";
import { Gift, Loader2, X } from "lucide-react";
import { useState } from "react";
import { giftCardsApi, normalizeGiftCard } from "../../lib/retailClient";
import type { PaymentDraft } from "./tenders";

interface GiftCardRowProps {
  draft: PaymentDraft;
  totalCents: number;
  currency: string;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
}

/** Spends a gift card toward the sale; the card is checked online because other tills may have spent it. */
export function GiftCardRow({ draft, totalCents, currency, disabled, onChange }: GiftCardRowProps) {
  const [code, setCode] = useState("");
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const applied = draft.giftCard ?? null;

  async function apply() {
    const normalized = normalizeGiftCard(code);
    if (!GIFT_CARD_CODE.test(normalized)) {
      setError("Gift card codes look like GC-AB12-CD34-EF56.");
      return;
    }
    setChecking(true);
    setError(null);
    try {
      const card = await giftCardsApi.lookup(normalized);
      if (card.currency !== currency) setError(`That card is in ${card.currency}; this register sells in ${currency}.`);
      else if (card.voided_at) setError("That gift card was voided.");
      else if (card.expires_at && new Date(card.expires_at) < new Date()) setError("That gift card has expired.");
      else if (card.balance_cents <= 0) setError("That gift card has been fully used.");
      else {
        onChange({ ...draft, giftCard: { code: card.code, balanceCents: card.balance_cents } });
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
          <Gift size={18} aria-hidden="true" className="shrink-0 text-primary" />
          <span className="min-w-0">
            <span className="block truncate font-semibold tabular-nums">{applied.code}</span>
            <span className="block text-xs text-zinc-600 tabular-nums dark:text-white/60">
              {formatMoney(used, currency)} used · {formatMoney(applied.balanceCents - used, currency)} left on the card
            </span>
          </span>
        </span>
        <button
          type="button"
          disabled={disabled}
          aria-label="Remove gift card"
          onClick={() => onChange({ ...draft, giftCard: null })}
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
          <span className="sr-only">Gift card code</span>
          <Gift size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            value={code}
            maxLength={24}
            disabled={disabled || nothingDue}
            onChange={(event) => setCode(event.target.value)}
            placeholder="Gift card (GC-…)"
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
