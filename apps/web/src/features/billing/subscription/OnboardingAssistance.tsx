import { formatMoney } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { Info } from "lucide-react";
import { useId, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

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
  const buttonRef = useRef<HTMLButtonElement>(null);
  const closeTimer = useRef<number | null>(null);
  const panelId = useId();
  const [place, setPlace] = useState({ top: 0, left: 0, width: 288 });

  const show = () => {
    if (closeTimer.current !== null) window.clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const hide = () => {
    closeTimer.current = window.setTimeout(() => setOpen(false), 120);
  };

  useLayoutEffect(() => {
    if (!open) return;
    const move = () => {
      const rect = buttonRef.current?.getBoundingClientRect();
      if (!rect) return;
      const width = Math.min(288, window.innerWidth - 24);
      const left = Math.min(Math.max(12, rect.left), Math.max(12, window.innerWidth - width - 12));
      const below = rect.bottom + 8;
      const height = 220;
      const top = below + height > window.innerHeight - 12 ? Math.max(12, rect.top - height - 8) : below;
      setPlace({ top, left, width });
    };
    move();
    window.addEventListener("resize", move);
    window.addEventListener("scroll", move, true);
    return () => {
      window.removeEventListener("resize", move);
      window.removeEventListener("scroll", move, true);
    };
  }, [open]);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={t("What is onboarding assistance?")}
        onClick={() => setOpen((current) => !current)}
        onMouseEnter={show}
        onMouseLeave={hide}
        onFocus={show}
        onBlur={hide}
        className="inline-flex size-5 items-center justify-center rounded-full text-charcoal/60 hover:text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-white/60 dark:hover:text-white"
      >
        <Info size={14} aria-hidden="true" />
      </button>
      {open && typeof document !== "undefined"
        ? createPortal(
            <div
              id={panelId}
              role="tooltip"
              onMouseEnter={show}
              onMouseLeave={hide}
              style={{ position: "fixed", top: place.top, left: place.left, width: place.width, zIndex: 80 }}
              className="rounded-xl border border-line bg-white p-3 text-start text-xs leading-5 text-charcoal shadow-lg dark:border-zinc-700 dark:bg-zinc-900 dark:text-white"
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
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
