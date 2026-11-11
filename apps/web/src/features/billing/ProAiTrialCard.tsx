import { formatMoney, type BillingCatalog } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiRequestError, apiGet, apiPost } from "../../lib/api";
import { usePractice } from "../onboarding/practice";

interface PromotionalTrial {
  eligible: boolean;
  reason: string | null;
  status: "not_started" | "active" | "expired" | "cancelled";
  base_plan_code: string | null;
  base_plan_name: string | null;
  promotional_plan_code: string;
  trial_days: number;
  starts_at: string | null;
  expires_at: string | null;
  days_remaining: number | null;
  capabilities: string[];
  enabled: boolean;
  reminder: string | null;
}

export function ProAiTrialCard() {
  const { t } = useLocale();
  const { practice, openGoLive } = usePractice();
  const [trial, setTrial] = useState<PromotionalTrial | null>(null);
  const [hidden, setHidden] = useState(() => sessionStorage.getItem("ai-pos.pro-ai-trial-hidden") === "1");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plans, setPlans] = useState<BillingCatalog["plans"]>([]);

  const load = () => {
    apiGet<PromotionalTrial>("/api/v1/billing/promotional-trial")
      .then(setTrial)
      .catch((caught: unknown) => {
        if (caught instanceof ApiRequestError && (caught.status === 403 || caught.status === 404)) {
          setTrial(null);
          return;
        }
        setError(caught instanceof ApiRequestError ? caught.message : "Could not load the trial.");
      });
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    if (trial?.status !== "expired") return;
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((catalog) => setPlans(catalog.plans.filter((plan) => plan.code === "GROWTH" || plan.code === "PRO_AI")))
      .catch(() => setPlans([]));
  }, [trial?.status]);

  if (trial === null) return error ? <p className="text-sm text-red-700">{error}</p> : null;
  if (hidden) return null;
  const showOffer = trial.eligible && trial.status === "not_started";
  const showStatus = trial.status === "active" || trial.status === "expired" || trial.status === "cancelled";
  if (!showOffer && !showStatus) return null;

  const dismiss = () => {
    sessionStorage.setItem("ai-pos.pro-ai-trial-hidden", "1");
    setHidden(true);
  };

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      setTrial(await apiPost<PromotionalTrial>("/api/v1/billing/promotional-trial", {}));
      setConfirming(false);
    } catch (caught) {
      setError(caught instanceof ApiRequestError ? caught.message : "Could not start the trial.");
    } finally {
      setBusy(false);
    }
  };

  const expiry = trial.expires_at ? new Date(trial.expires_at).toLocaleString() : "";

  return (
    <section className="rounded-2xl border border-accent/30 bg-accent/5 px-4 py-3 text-sm">
      <p className="font-semibold text-charcoal">{t("Pro AI Trial")}</p>
      {showOffer ? (
        <>
          <h2 className="mt-1 text-base font-semibold">{t("Try Pro AI free for {days} days", { days: trial.trial_days })}</h2>
          <p className="mt-1 text-charcoal/70">
            {t(
              "Explore AxizPOS Pro AI for {days} days. Your current plan stays in place. When the trial ends, the account returns to that plan. Business data and sales stay. There is no payment and no automatic charge.",
              { days: trial.trial_days },
            )}
          </p>
          <p className="mt-2 text-charcoal/70">
            {t("Your current plan")}: {trial.base_plan_name ?? trial.base_plan_code}. {t("No payment is required.")}
          </p>
          {trial.capabilities.length > 0 ? (
            <ul className="mt-2 list-disc pl-5 text-charcoal/80">
              {trial.capabilities.map((label) => (
                <li key={label}>{label}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-charcoal/70">{t("Pro AI resource limits apply during the trial.")}</p>
          )}
          <p className="mt-1 text-charcoal/60">{t("Optional plugins stay separate and are not included.")}</p>
          {error ? <p className="mt-2 text-red-700">{error}</p> : null}
          <div className="mt-3 flex flex-wrap gap-2">
            {confirming ? (
              <button type="button" className="rounded-full bg-accent px-4 py-2 font-semibold text-white disabled:opacity-60" disabled={busy} onClick={() => void start()}>
                {busy ? "…" : t("Confirm trial")}
              </button>
            ) : (
              <button type="button" className="rounded-full bg-accent px-4 py-2 font-semibold text-white" onClick={() => setConfirming(true)}>
                {t("Start {days}-day free trial", { days: trial.trial_days })}
              </button>
            )}
            <button type="button" className="rounded-full border border-line bg-white px-4 py-2" onClick={dismiss}>
              {t("Not now")}
            </button>
          </div>
        </>
      ) : (
        <>
          <p className="mt-1 text-charcoal/80">{trial.reminder}</p>
          {expiry ? <p className="mt-1 text-charcoal/60">{expiry}</p> : null}
          <p className="mt-1 text-charcoal/60">
            {t("Base plan")}: {trial.base_plan_name ?? trial.base_plan_code}
          </p>
          {trial.capabilities.length > 0 ? (
            <ul className="mt-2 list-disc pl-5">
              {trial.capabilities.map((label) => (
                <li key={label}>{label}</li>
              ))}
            </ul>
          ) : null}
          <div className="mt-3 flex flex-wrap gap-3">
            <Link to="/subscription?plan=PRO_AI" className="font-semibold text-accent">
              {t("View plans")}
            </Link>
            {trial.status === "expired" && practice ? (
              <button type="button" className="font-semibold text-accent" onClick={openGoLive}>
                {t("Choose a plan")}
              </button>
            ) : null}
            {trial.status === "expired" ? (
              <button type="button" className="text-charcoal/70" onClick={dismiss}>
                {t("Continue on this plan")}
              </button>
            ) : null}
          </div>
          {trial.status === "expired" && plans.length > 0 ? (
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {plans.map((plan) => (
                <li key={plan.code} className="rounded-xl border border-line bg-white px-3 py-2">
                  <p className="font-semibold">{plan.name}</p>
                  <p className="tabular-nums">{plan.custom_pricing ? "Custom" : `${formatMoney(plan.monthly_fils, "AED")} / month`}</p>
                </li>
              ))}
            </ul>
          ) : null}
        </>
      )}
    </section>
  );
}
