import { formatMoney } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { Info } from "lucide-react";
import { useId, useState } from "react";

/** Catalog price for optional setup help. It is not part of the subscription. */
export function OnboardingAssistanceNote({ amountFils, currency }: { amountFils: number; currency: string }) {
  const { t } = useLocale();
  const amount = formatMoney(amountFils, currency);
  return (
    <div className="mt-2 rounded-xl bg-zinc-50 px-3 py-2 text-charcoal dark:bg-white/5 dark:text-white">
      <div className="flex items-center gap-1">
        <p className="text-sm font-semibold">{t("Optional onboarding assistance")}</p>
        <OnboardingHelp amount={amount} />
      </div>
      <p className="mt-0.5 text-sm tabular-nums" dir="ltr">
        {t("{price} one-time", { price: amount })}
      </p>
    </div>
  );
}

export function OnboardingHelp({ amount }: { amount: string }) {
  const { t } = useLocale();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <span className="relative inline-flex" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t("What is onboarding assistance?")}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex size-5 items-center justify-center rounded-full text-charcoal/60 hover:text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-white/60 dark:hover:text-white"
      >
        <Info size={14} aria-hidden="true" />
      </button>
      {open ? (
        <span
          id={panelId}
          role="tooltip"
          className="absolute start-0 top-7 z-30 w-[min(18rem,calc(100vw-3rem))] rounded-xl border border-line bg-white p-3 text-start text-xs leading-5 text-charcoal shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
        >
          <strong className="block text-sm">{t("What is onboarding assistance?")}</strong>
          <p className="mt-1">
            {t(
              "Our onboarding assistance helps you get started with AxizPOS. Our team can guide you through your initial setup, business configuration, product and inventory setup, staff setup, and basic system training.",
            )}
          </p>
          <p className="mt-1">
            {t(
              "This is an optional service. You can subscribe to AxizPOS without purchasing onboarding assistance and configure your business yourself.",
            )}
          </p>
          <p className="mt-2 font-semibold" dir="ltr">
            {t("One-time fee: {amount}", { amount })}
          </p>
        </span>
      ) : null}
    </span>
  );
}
