import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";

const ease = [0.4, 0, 0.2, 1] as const;

/** The same action bar on every signup step. Continue stays a content-sized button on the right. */
export function WizardFooter({
  continueLabel,
  busyLabel = "Saving…",
  disabled = false,
  busy = false,
  type = "button",
  href,
  onContinue,
  onBack,
  backLabel = "Back",
}: {
  continueLabel?: string;
  busyLabel?: string;
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  href?: string;
  onContinue?: () => void;
  onBack?: () => void;
  backLabel?: string;
}) {
  const reduced = useReducedMotion() === true;
  const { t } = useLocale();
  const label = busy ? t(busyLabel) : continueLabel ? t(continueLabel) : undefined;
  const buttonClass =
    "inline-flex h-12 min-w-[9rem] items-center justify-center rounded-xl bg-accent px-5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-40";

  return (
    <footer className="signup-footer mt-0 flex shrink-0 items-center justify-between gap-3 border-t border-line bg-white pt-3 pb-[max(0.25rem,env(safe-area-inset-bottom))]">
      {onBack ? (
        <button type="button" onClick={onBack} className="h-12 rounded-xl px-4 text-sm font-medium text-charcoal/70 hover:bg-surface">
          {t(backLabel)}
        </button>
      ) : (
        <span />
      )}
      {label ? (
        href ? (
          <a href={href} className={buttonClass}>
            {label}
          </a>
        ) : (
          <motion.button
            type={type}
            disabled={disabled || busy}
            onClick={type === "button" ? onContinue : undefined}
            className={buttonClass}
            whileTap={reduced || disabled ? undefined : { scale: 0.98 }}
          >
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={label}
                initial={reduced ? false : { opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={reduced ? undefined : { opacity: 0, y: -4 }}
                transition={{ duration: reduced ? 0 : 0.18, ease }}
              >
                {label}
              </motion.span>
            </AnimatePresence>
          </motion.button>
        )
      ) : null}
    </footer>
  );
}
