import { formatMoney } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import type { PriceView } from "./display";

/** One price treatment for plans and add-ons. Amounts come from the catalog or the quote. */
export function PriceDisplay({ view, prominent = false }: { view: PriceView; prominent?: boolean }) {
  const { t } = useLocale();
  if (view.kind === "unpriced") {
    return <p className="text-sm font-semibold text-charcoal dark:text-white">{t("Price not configured")}</p>;
  }
  if (view.kind === "custom") {
    return <p className={`${prominent ? "text-2xl" : "text-sm"} font-semibold text-charcoal dark:text-white`}>{t("Custom pricing")}</p>;
  }
  if (view.kind === "loading") {
    return <p className="text-sm text-charcoal/50 dark:text-white/50">{t("Loading price")}</p>;
  }
  if (view.kind === "error") {
    return <p className="text-xs text-amber-800 dark:text-amber-200">{view.message}</p>;
  }
  if (view.kind === "none") return null;

  return (
    <div className="grid gap-0.5">
      {view.lines.map((line) => {
        const amount = formatMoney(line.fils, line.currency);
        const cycle =
          line.cadence === "cycle" && line.periodName ? t("/ {cycle}", { cycle: t(line.periodName) }) : null;
        const text = cycle
          ? null
          : line.cadence === "month"
            ? t("{price} per month", { price: amount })
            : line.cadence === "once"
              ? t("{price} one-time", { price: amount })
              : line.cadence === "deposit"
                ? t("{price} refundable deposit", { price: amount })
                : amount;
        return (
          <p
            key={`${line.cadence}-${line.fils}`}
            dir="ltr"
            className={`text-start font-semibold tabular-nums text-charcoal dark:text-white ${prominent ? "text-2xl tracking-tight" : "text-sm"}`}
          >
            {cycle ? (
              <>
                {amount}
                <sub className="ms-1 whitespace-nowrap text-[0.62em] font-medium tracking-normal">{cycle}</sub>
              </>
            ) : (
              text
            )}
          </p>
        );
      })}
      {view.discountBps != null && view.discountBps > 0 ? (
        <p className="text-xs font-medium text-accent">{t("{percent}% off this cycle", { percent: view.discountBps / 100 })}</p>
      ) : null}
    </div>
  );
}
