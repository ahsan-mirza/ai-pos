import { formatMoney } from "@ai-pos/shared-types";
import { BrandLogo } from "@ai-pos/ui";
import { Lock } from "lucide-react";
import { useState } from "react";
import { openShift } from "../../lib/tauri";
import type { CashierSession } from "../auth/session";
import { store } from "../checkout/catalog";
import { syncBusinessCurrency, useBusinessCurrency } from "../checkout/currency";
import { parseAmount, setShift } from "./shift";

const quickFloats = [0, 20_000, 50_000, 100_000];

/** Shown after unlock until the cashier counts the opening float; the register cannot sell without a shift. */
export function OpenShiftScreen({ session, onLock }: { session: CashierSession; onLock: () => void }) {
  const currency = useBusinessCurrency();
  const [amount, setAmount] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const cents = parseAmount(amount);

  const submit = async () => {
    if (busy || cents === null) return;
    setBusy(true);
    setError(null);
    try {
      const counted = await syncBusinessCurrency();
      setShift(
        await openShift({
          id: crypto.randomUUID(),
          opened_at: new Date().toISOString(),
          opening_float_cents: cents,
          currency: counted || currency,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-charcoal p-6 font-sans text-white">
      <div className="w-full max-w-lg rounded-[28px] bg-white/5 p-8">
        <div className="flex items-center justify-between">
          <BrandLogo tone="dark" className="h-10 w-auto" />
          <button
            type="button"
            onClick={onLock}
            className="inline-flex items-center gap-2 rounded-full px-3 py-2 text-sm text-white/60 hover:bg-white/10 hover:text-white"
          >
            <Lock size={15} aria-hidden="true" /> Lock
          </button>
        </div>
        <p className="mt-10 text-xs font-medium uppercase tracking-[0.18em] text-white/50">{store.name}</p>
        <h1 className="mt-2 text-3xl font-semibold">Open shift</h1>
        <p className="mt-2 text-sm text-white/60">
          {session.user.full_name}, count the cash in the drawer before the first sale. The close is blind: you count
          again at the end without seeing what the register expects.
        </p>
        <form
          className="mt-8"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <label className="block text-sm font-medium text-white/80" htmlFor="opening-float">
            Opening float ({currency})
            <input
              id="opening-float"
              autoFocus
              inputMode="decimal"
              autoComplete="off"
              value={amount}
              onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
              placeholder="0.00"
              className="mt-2 h-16 w-full rounded-2xl border border-white/10 bg-white/5 px-4 text-2xl font-semibold tabular-nums text-white outline-none focus:border-primary"
            />
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            {quickFloats.map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setAmount((value / 100).toFixed(2))}
                className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold tabular-nums hover:bg-white/20"
              >
                {formatMoney(value, currency)}
              </button>
            ))}
          </div>
          <p role="alert" className="mt-4 min-h-5 text-sm text-red-400">
            {cents === null ? "Enter an amount like 200.00." : error}
          </p>
          <button
            type="submit"
            disabled={busy || cents === null}
            className="mt-2 h-14 w-full rounded-2xl bg-primary text-base font-semibold disabled:opacity-40"
          >
            {busy ? "Opening…" : `Open shift with ${formatMoney(cents ?? 0, currency)}`}
          </button>
        </form>
      </div>
    </div>
  );
}
