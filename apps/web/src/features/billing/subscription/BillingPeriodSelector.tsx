import type { BillingCycle } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { selectorDiscountBps } from "./display";

export function BillingPeriodSelector({
  cycles,
  value,
  annualDiscountBps,
  onChange,
}: {
  cycles: BillingCycle[];
  value: string;
  annualDiscountBps: number | null | undefined;
  onChange: (code: string) => void;
}) {
  const { t } = useLocale();
  if (cycles.length === 0) return null;
  return (
    <div role="radiogroup" aria-label={t("Billing cycle")} className="flex max-w-full flex-wrap gap-1 rounded-full bg-zinc-100 p-1 dark:bg-zinc-800">
      {cycles.map((cycle) => {
        const bps = selectorDiscountBps(cycle, annualDiscountBps);
        const selected = cycle.code === value;
        return (
          <button
            key={cycle.code}
            type="button"
            role="radio"
            aria-checked={selected}
            onClick={() => onChange(cycle.code)}
            className={`inline-flex h-9 items-center rounded-full px-3 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${
              selected ? "bg-white font-semibold text-charcoal dark:bg-zinc-900 dark:text-white" : "text-charcoal/70 dark:text-white/70"
            }`}
          >
            {t(cycle.name)}
            {bps > 0 ? <span className="ms-1 text-xs font-medium text-accent">{t("{percent}% off", { percent: bps / 100 })}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
