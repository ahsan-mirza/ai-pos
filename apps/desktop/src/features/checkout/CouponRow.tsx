import type { Promotion } from "@ai-pos/shared-types";
import { Tag, X } from "lucide-react";
import { useState } from "react";
import { couponKnown } from "./promotions";

interface CouponRowProps {
  promotions: Promotion[];
  coupon: string | null;
  disabled: boolean;
  onChange: (coupon: string | null) => void;
}

/** Apply or remove a coupon code. Automatic promotion savings are listed in the sale summary. */
export function CouponRow({ promotions, coupon, disabled, onChange }: CouponRowProps) {
  const [typing, setTyping] = useState("");
  const [error, setError] = useState<string | null>(null);
  const applied = coupon ? couponKnown(promotions, coupon) : null;

  if (applied) {
    return (
      <div className="flex items-center justify-between gap-3 rounded-2xl border border-zinc-200 px-3 py-1.5 text-sm dark:border-zinc-800">
        <span className="flex min-w-0 items-center gap-2.5">
          <Tag size={16} aria-hidden="true" className="shrink-0 text-primary" />
          <span className="min-w-0">
            <span className="block font-mono font-semibold">{applied.coupon_code}</span>
            <span className="block truncate text-xs text-zinc-600 dark:text-white/60">{applied.name}</span>
          </span>
        </span>
        <button
          type="button"
          aria-label="Remove coupon"
          disabled={disabled}
          onClick={() => onChange(null)}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-zinc-500 hover:bg-zinc-100 dark:hover:bg-white/10"
        >
          <X size={15} aria-hidden="true" />
        </button>
      </div>
    );
  }

  return (
    <div>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (!typing.trim()) return;
          if (!couponKnown(promotions, typing)) {
            setError("That coupon is not valid at this register.");
            return;
          }
          setError(null);
          onChange(typing.trim().toUpperCase());
          setTyping("");
        }}
      >
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Coupon code</span>
          <Tag size={15} aria-hidden="true" className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-zinc-400" />
          <input
            value={typing}
            maxLength={32}
            disabled={disabled}
            onChange={(event) => setTyping(event.target.value)}
            placeholder="Coupon code"
            className="h-10 w-full rounded-2xl border border-zinc-200 bg-white pl-9 pr-3 font-mono text-sm uppercase placeholder:font-sans placeholder:normal-case focus:border-primary focus:outline-none dark:border-zinc-800 dark:bg-zinc-900/60"
          />
        </label>
        <button
          type="submit"
          disabled={disabled || !typing.trim()}
          className="h-10 rounded-2xl bg-zinc-900 px-4 text-xs font-semibold text-white disabled:opacity-40 dark:bg-white dark:text-zinc-900"
        >
          Apply
        </button>
      </form>
      {error ? (
        <p role="alert" className="mt-1 text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}
