import { formatMoney, type ProductUpsert, type TradeIn } from "@ai-pos/shared-types";
import { Repeat2, X } from "lucide-react";
import { useState } from "react";
import { recordCashMovement, type RegisterCustomer } from "../../lib/tauri";
import { cancelTradeIn } from "./tradeIn";
import { TradeInModal } from "./TradeInModal";
import type { PaymentDraft } from "./tenders";

interface TradeInRowProps {
  draft: PaymentDraft;
  products: ProductUpsert[];
  cashierId: string;
  customer: RegisterCustomer | null;
  currency: string;
  saleCents: number;
  disabled: boolean;
  onChange: (draft: PaymentDraft) => void;
}

export function TradeInRow({ draft, products, cashierId, customer, currency, saleCents, disabled, onChange }: TradeInRowProps) {
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const applied = draft.tradeIn ?? null;

  async function done(tradeIn: TradeIn) {
    setOpen(false);
    setError(null);
    if (tradeIn.payout === "SALE_CREDIT") {
      onChange({ ...draft, tradeIn: { id: tradeIn.id, number: tradeIn.number, amountCents: tradeIn.offer_cents } });
      setNotice(null);
      return;
    }
    if (tradeIn.payout === "CASH" && tradeIn.offer_cents > 0) {
      await recordCashMovement({
        id: crypto.randomUUID(),
        kind: "PAY_OUT",
        amount_cents: tradeIn.offer_cents,
        reason: `Trade-in ${tradeIn.number}`,
        occurred_at: new Date().toISOString(),
      }).catch(() => undefined);
      setNotice(`${tradeIn.number}: pay the customer ${formatMoney(tradeIn.offer_cents, currency)} from the drawer.`);
      return;
    }
    setNotice(
      tradeIn.store_credit_code
        ? `${tradeIn.number}: give the customer voucher ${tradeIn.store_credit_code} worth ${formatMoney(tradeIn.offer_cents, currency)}.`
        : `${tradeIn.number} recorded.`,
    );
  }

  async function remove() {
    if (!applied) return;
    try {
      await cancelTradeIn(applied.id);
      onChange({ ...draft, tradeIn: null });
      setError(null);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    }
  }

  return (
    <div className="space-y-2">
      {applied ? (
        <div className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200 bg-white/[0.03] px-3 py-1.5 text-sm dark:border-zinc-800">
          <span className="flex min-w-0 items-center gap-2.5">
            <Repeat2 size={18} aria-hidden="true" className="shrink-0 text-primary" />
            <span className="min-w-0">
              <span className="block truncate font-semibold">Trade-in {applied.number}</span>
              <span className="block text-xs text-zinc-600 tabular-nums dark:text-white/60">−{formatMoney(applied.amountCents, currency)} off this sale</span>
            </span>
          </span>
          <button
            type="button"
            disabled={disabled}
            aria-label="Cancel the trade-in"
            onClick={() => void remove()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 disabled:opacity-40 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X size={16} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          onClick={() => setOpen(true)}
          className="flex h-10 w-full items-center gap-2 rounded-2xl border border-dashed border-zinc-300 px-3 text-left text-sm font-medium text-zinc-600 transition-colors hover:border-primary hover:text-primary disabled:opacity-40 dark:border-zinc-700 dark:text-white/60"
        >
          <Repeat2 size={16} aria-hidden="true" />
          Customer trading in a device?
        </button>
      )}
      {notice ? (
        <p role="status" className="rounded-xl bg-emerald-500/10 px-3 py-2 text-xs font-medium text-emerald-700 dark:text-emerald-300">
          {notice}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-xs font-medium text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
      {open ? (
        <TradeInModal
          products={products}
          cashierId={cashierId}
          customer={customer}
          currency={currency}
          saleCents={saleCents}
          onClose={() => setOpen(false)}
          onDone={(tradeIn) => void done(tradeIn)}
        />
      ) : null}
    </div>
  );
}
