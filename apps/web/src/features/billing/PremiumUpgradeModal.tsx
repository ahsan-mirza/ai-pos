import { formatMoney } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { LockKeyhole, Puzzle, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { Link } from "react-router-dom";
import { ApiRequestError, apiPost } from "../../lib/api";
import type { FeatureAccess } from "../../lib/featureAccess";

export function PremiumUpgradeModal({
  feature,
  onClose,
  onTrialStarted,
}: {
  feature: FeatureAccess;
  onClose: () => void;
  onTrialStarted: () => void;
}) {
  const { t } = useLocale();
  const reduce = useReducedMotion();
  const titleId = useId();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const plugin = feature.state === "PLUGIN_REQUIRED";
  const label = t(feature.label);
  const title = plugin ? t("Add {feature}", { feature: label }) : t("Unlock {feature}", { feature: label });
  const current = t(feature.current_plan_name ?? "your current plan");
  const required = t(feature.required_plan_name ?? feature.plugin_name ?? "");
  const country = feature.state === "COUNTRY_UNAVAILABLE";
  const disabled = feature.state === "FEATURE_DISABLED" || feature.state === "BUSINESS_TYPE_UNAVAILABLE";
  const restricted = feature.state === "SUBSCRIPTION_RESTRICTED";
  const upgrade = feature.state === "UPGRADE_REQUIRED";

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function startTrial() {
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/v1/billing/promotional-trial", {});
      onTrialStarted();
      onClose();
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : t("Could not start the trial."));
    } finally {
      setBusy(false);
    }
  }

  const price =
    feature.price_published && feature.price_fils !== null && feature.currency
      ? formatMoney(feature.price_fils, feature.currency)
      : null;

  return (
    <div className="fixed inset-0 z-[70] flex items-end justify-center p-4 sm:items-center" role="presentation">
      <button type="button" className="absolute inset-0 bg-charcoal/40" aria-label={t("Not now")} onClick={onClose} />
      <AnimatePresence>
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby={titleId}
          initial={reduce ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={reduce ? undefined : { opacity: 0, y: 8 }}
          transition={{ duration: 0.18 }}
          className="relative flex max-h-[90vh] w-full max-w-md flex-col overflow-hidden rounded-3xl border border-gray-100 bg-white shadow-2xl dark:border-gray-800 dark:bg-[#222026]"
        >
          <header className="flex items-start justify-between gap-4 px-6 pb-2 pt-6">
            <div className="flex min-w-0 items-start gap-3">
              <span className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent/10 text-accent">
                {plugin ? <Puzzle aria-hidden="true" size={18} /> : <LockKeyhole aria-hidden="true" size={18} />}
              </span>
              <div className="min-w-0">
                <h2 id={titleId} className="text-lg font-semibold text-charcoal dark:text-white">
                  {title}
                </h2>
                <p className="mt-1 text-sm text-charcoal/70 dark:text-white/70">{t(feature.description)}</p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              autoFocus
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-charcoal/60 hover:bg-charcoal/[0.05]"
              aria-label={t("Not now")}
            >
              <X size={18} aria-hidden="true" />
            </button>
          </header>
          <div className="space-y-4 overflow-y-auto px-6 py-4 text-sm">
            <p className="text-charcoal/80 dark:text-white/80">
              {plugin
                ? t("{feature} is purchased separately. It is not included when you change the base plan.", {
                    feature: label,
                  })
                : country
                  ? t("{plan} is not sold in this store's country.", { plan: required })
                  : disabled
                    ? feature.state === "BUSINESS_TYPE_UNAVAILABLE"
                      ? t("{feature} is not available for this business type.", { feature: label })
                      : t("{feature} is turned off.", { feature: label })
                    : restricted
                      ? t("Paid features stay locked until the subscription is active.")
                      : t("{feature} is not included in your current {plan} plan.", {
                          feature: label,
                          plan: current,
                        })}
            </p>
            {upgrade || plugin ? (
              <dl className="grid grid-cols-2 gap-3 rounded-2xl bg-[#f8fafc] p-4 dark:bg-white/5">
                <div>
                  <dt className="text-xs text-charcoal/50">{t("Current plan")}</dt>
                  <dd className="mt-1 font-semibold">{current}</dd>
                </div>
                <div>
                  <dt className="text-xs text-charcoal/50">{plugin ? t("Plugin") : t("Required plan")}</dt>
                  <dd className="mt-1 font-semibold">{required}</dd>
                </div>
                <div className="col-span-2">
                  <dt className="text-xs text-charcoal/50">{t("Price")}</dt>
                  <dd className="mt-1 font-semibold tabular-nums">
                    {feature.custom_pricing
                      ? t("Custom pricing")
                      : price
                        ? t("{price} per month", { price })
                        : t("The price is published in the console.")}
                  </dd>
                </div>
              </dl>
            ) : null}
            {upgrade && feature.benefits.length > 0 ? (
              <ul className="space-y-1 text-charcoal/75 dark:text-white/75">
                {feature.benefits.map((item) => (
                  <li key={item}>{t(item)}</li>
                ))}
              </ul>
            ) : null}
            {error ? <p className="text-red-700">{error}</p> : null}
          </div>
          <footer className="flex flex-wrap items-center justify-end gap-3 border-t border-line px-6 py-4">
            <button type="button" onClick={onClose} className="h-10 px-3 text-sm font-medium text-charcoal/70">
              {t("Not now")}
            </button>
            {upgrade && feature.trial_available ? (
              <button
                type="button"
                disabled={busy}
                onClick={() => void startTrial()}
                className="inline-flex h-10 items-center rounded-lg border border-line px-4 text-sm font-semibold"
              >
                {busy ? t("Please wait…") : t("Start Pro AI trial")}
              </button>
            ) : null}
            {restricted || country || disabled ? (
              <Link
                to="/subscription"
                onClick={onClose}
                className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                {t("View plans")}
              </Link>
            ) : plugin ? (
              <Link
                to={feature.plugin_code ? `/subscription?plugin=${encodeURIComponent(feature.plugin_code)}` : "/subscription#plugins"}
                onClick={onClose}
                className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                {t("Explore add-ons")}
              </Link>
            ) : feature.custom_pricing ? (
              <Link
                to="/subscription?plan=ENTERPRISE"
                onClick={onClose}
                className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                {t("Contact sales")}
              </Link>
            ) : (
              <Link
                to={feature.required_plan ? `/subscription?plan=${encodeURIComponent(feature.required_plan)}` : "/subscription#plans"}
                onClick={onClose}
                className="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white hover:bg-accent-hover"
              >
                {required ? t("View {plan}", { plan: required }) : t("View plans")}
              </Link>
            )}
          </footer>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
