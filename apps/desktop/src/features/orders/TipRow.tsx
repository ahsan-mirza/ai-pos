import { formatMoney } from "@ai-pos/shared-types";
import { HandCoins } from "lucide-react";
import { useState } from "react";

interface TipRowProps {
  /** The bill the presets are a share of (after service charge, before the tip). */
  billCents: number;
  presetsBps: number[];
  tipCents: number;
  currency: string;
  disabled: boolean;
  onChange: (cents: number) => void;
}

/** Tip on top of the bill: preset percentages or a typed amount. Tips are owed to staff, never taxed. */
export function TipRow({ billCents, presetsBps, tipCents, currency, disabled, onChange }: TipRowProps) {
  const [custom, setCustom] = useState("");
  const presetCents = (bps: number) => Math.floor((billCents * bps + 5000) / 10_000);
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-zinc-500 dark:text-white/50">
        <HandCoins size={13} aria-hidden="true" /> Tip
      </span>
      <button
        type="button"
        disabled={disabled}
        aria-pressed={tipCents === 0}
        onClick={() => {
          setCustom("");
          onChange(0);
        }}
        className={`h-7 rounded-full px-2.5 text-[11px] font-semibold ${tipCents === 0 ? "bg-primary text-white" : "bg-zinc-200/70 dark:bg-white/10"}`}
      >
        None
      </button>
      {presetsBps.map((bps) => {
        const cents = presetCents(bps);
        const active = tipCents > 0 && tipCents === cents && custom === "";
        return (
          <button
            key={bps}
            type="button"
            disabled={disabled || billCents === 0}
            aria-pressed={active}
            title={formatMoney(cents, currency)}
            onClick={() => {
              setCustom("");
              onChange(cents);
            }}
            className={`h-7 rounded-full px-2.5 text-[11px] font-semibold tabular-nums ${active ? "bg-primary text-white" : "bg-zinc-200/70 dark:bg-white/10"}`}
          >
            {bps / 100}%
          </button>
        );
      })}
      <input
        aria-label="Tip amount"
        inputMode="decimal"
        disabled={disabled}
        value={custom}
        placeholder="Other"
        onChange={(event) => {
          const value = event.target.value.replace(/[^\d.]/g, "");
          setCustom(value);
          const cents = Math.round((Number.parseFloat(value || "0") || 0) * 100);
          onChange(Math.max(0, cents));
        }}
        className="h-7 w-20 rounded-full border border-zinc-200 bg-white px-2.5 text-right text-[11px] font-semibold tabular-nums focus:border-primary focus:outline-none dark:border-white/10 dark:bg-zinc-900/60"
      />
    </div>
  );
}
