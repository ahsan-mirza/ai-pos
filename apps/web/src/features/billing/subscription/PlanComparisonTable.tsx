import type { BillingPlan, MarketplaceItem } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useMemo, useState } from "react";
import { isCustomPlan, isFreePlan } from "../subscriptionPlans";
import {
  addonIndex,
  categorySlug,
  comparisonCell,
  differingFeatures,
  featureRecommendation,
  groupFeatures,
  planLimitCell,
  upgradeRecommendation,
  type ComparableFeature,
  type ComparisonContext,
  type UsageMetricView,
} from "./display";
import { FeatureBadge } from "./FeatureBadge";

const LIMITS = [
  ["branches", "Branches"],
  ["registers", "Registers"],
  ["staff", "Staff"],
  ["products", "Products"],
  ["customers", "Customers"],
] as const;

export function PlanComparisonTable({
  plans,
  features,
  currentCode = null,
  items = [],
  usage = [],
  onSelectPlan,
}: {
  plans: BillingPlan[];
  features: ComparableFeature[];
  currentCode?: string | null;
  items?: readonly MarketplaceItem[];
  usage?: UsageMetricView[];
  onSelectPlan?: (plan: BillingPlan) => void;
}) {
  const { t } = useLocale();
  const [differencesOnly, setDifferencesOnly] = useState(false);
  const context = useMemo<ComparisonContext>(() => {
    const index = addonIndex(items);
    const claimedKeys = new Set(plans.flatMap((plan) => plan.included_modules));
    return { currentCode, purchasedKeys: index.purchasedKeys, addons: index.addons, claimedKeys };
  }, [currentCode, items, plans]);
  const source = useMemo(
    () => (differencesOnly ? differingFeatures(features, plans, context) : features),
    [differencesOnly, features, plans, context],
  );
  const groups = useMemo(() => groupFeatures(source), [source]);
  const capacity = upgradeRecommendation(usage, plans, currentCode);
  const feature = featureRecommendation(features, plans, context);

  return (
    <div className="grid min-w-0 grid-cols-[minmax(0,1fr)] gap-3">
      {capacity ? (
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-charcoal dark:border-zinc-800 dark:bg-zinc-900 dark:text-white">
          {t("{plan} includes a higher {metric} allowance.", { plan: t(capacity.plan.name), metric: t(capacity.metric) })}{" "}
          <PlanLink plan={capacity.plan} contact={capacity.contact} onSelectPlan={onSelectPlan} />
        </p>
      ) : null}
      {feature?.kind === "plan" ? (
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-charcoal dark:border-zinc-800 dark:bg-zinc-900 dark:text-white">
          {feature.contact
            ? t("{feature} is arranged on {plan}.", { feature: t(feature.feature), plan: t(feature.plan.name) })
            : t("{feature} is included in {plan}.", { feature: t(feature.feature), plan: t(feature.plan.name) })}{" "}
          <PlanLink plan={feature.plan} contact={feature.contact} onSelectPlan={onSelectPlan} />
        </p>
      ) : null}
      {feature?.kind === "addon" ? (
        <p className="rounded-2xl border border-line bg-white px-4 py-3 text-sm text-charcoal dark:border-zinc-800 dark:bg-zinc-900 dark:text-white">
          {t("{feature} is available as the {addon} add-on.", { feature: t(feature.feature), addon: feature.name })}
        </p>
      ) : null}
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 max-w-full gap-2 overflow-x-auto" role="navigation" aria-label={t("Feature comparison")}>
          {groups.map((group) => (
            <button
              key={group.label}
              type="button"
              onClick={() => document.getElementById(`compare-${categorySlug(group.label)}`)?.scrollIntoView({ block: "start" })}
              className="inline-flex h-9 shrink-0 items-center rounded-full border border-line px-3 text-xs font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-white"
            >
              {t(group.label)}
            </button>
          ))}
          <button
            type="button"
            onClick={() => document.getElementById("compare-resource-limits")?.scrollIntoView({ block: "start" })}
            className="inline-flex h-9 shrink-0 items-center rounded-full border border-line px-3 text-xs font-semibold text-charcoal focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent dark:text-white"
          >
            {t("Resource limits")}
          </button>
        </div>
        <button
          type="button"
          aria-pressed={differencesOnly}
          onClick={() => setDifferencesOnly((current) => !current)}
          className="inline-flex h-9 items-center rounded-full border border-line px-3 text-xs font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent"
        >
          {differencesOnly ? t("Show all features") : t("Show differences only")}
        </button>
      </div>
      <p className="text-xs text-charcoal/60 dark:text-white/60">{t("Scroll sideways to compare plans.")}</p>
      {groups.length === 0 ? (
        <p className="text-sm text-charcoal/60">{t("No features are published for this business.")}</p>
      ) : (
        <div className="min-w-0 max-w-full overflow-x-auto rounded-2xl border border-line bg-white dark:border-zinc-800 dark:bg-zinc-900">
          <table className="w-full min-w-[44rem] border-collapse text-sm">
            <thead className="sticky top-0 z-10">
              <tr className="border-b border-line text-start">
                <th className="sticky start-0 z-20 bg-white px-4 py-3 text-start font-semibold dark:bg-zinc-900">{t("Feature")}</th>
                {plans.map((plan) => (
                  <th key={plan.code} className={`px-3 py-3 text-start font-semibold ${plan.code === currentCode ? "bg-accent/10" : "bg-white dark:bg-zinc-900"}`}>
                    <span className="block">{t(plan.name)}</span>
                    {plan.code === currentCode ? <span className="mt-1 block text-xs font-semibold text-accent">{t("Current plan")}</span> : null}
                    {isCustomPlan(plan) ? <span className="mt-1 block text-xs font-medium text-charcoal/60 dark:text-white/60">{t("Custom")}</span> : null}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {groups.map((group) => (
                <GroupRows key={group.label} label={group.label} rows={group.rows} plans={plans} context={context} />
              ))}
              <LimitRows plans={plans} currentCode={currentCode} usage={usage} />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function PlanLink({
  plan,
  contact,
  onSelectPlan,
}: {
  plan: BillingPlan;
  contact: boolean;
  onSelectPlan?: (plan: BillingPlan) => void;
}) {
  const { t } = useLocale();
  if (contact || isCustomPlan(plan) || isFreePlan(plan)) {
    return (
      <a href={`#plan-${plan.code}`} className="font-semibold text-accent">
        {t("View plan")}
      </a>
    );
  }
  return (
    <button type="button" onClick={() => onSelectPlan?.(plan)} className="font-semibold text-accent">
      {t("Review quote")}
    </button>
  );
}

function GroupRows({
  label,
  rows,
  plans,
  context,
}: {
  label: string;
  rows: ComparableFeature[];
  plans: BillingPlan[];
  context: ComparisonContext;
}) {
  const { t } = useLocale();
  return (
    <>
      <tr id={`compare-${categorySlug(label)}`} className="scroll-mt-24 bg-zinc-50 dark:bg-white/5">
        <th colSpan={plans.length + 1} className="px-4 py-2 text-start text-xs font-semibold uppercase tracking-wide text-charcoal/50">
          {t(label)}
        </th>
      </tr>
      {rows.map((feature) => (
        <tr key={feature.feature_key} className="border-t border-line">
          <th className="sticky start-0 bg-white px-4 py-2 text-start font-medium dark:bg-zinc-900">
            <span>{t(feature.label)}</span>
            {feature.description ? (
              <details className="mt-1">
                <summary className="cursor-pointer text-xs font-normal text-charcoal/60 dark:text-white/60">{t("View details")}</summary>
                <p className="mt-1 max-w-xs text-xs font-normal text-charcoal/70 dark:text-white/70" dir="auto">{feature.description}</p>
              </details>
            ) : null}
          </th>
          {plans.map((plan) => (
            <td key={plan.code} className={`px-3 py-2 ${plan.code === context.currentCode ? "bg-accent/5" : ""}`}>
              <FeatureBadge mark={comparisonCell(plan, feature, context)} />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

function LimitRows({
  plans,
  currentCode,
  usage,
}: {
  plans: BillingPlan[];
  currentCode: string | null;
  usage: UsageMetricView[];
}) {
  const { t } = useLocale();
  return (
    <>
      <tr id="compare-resource-limits" className="scroll-mt-24 bg-zinc-50 dark:bg-white/5">
        <th colSpan={plans.length + 1} className="px-4 py-2 text-start text-xs font-semibold uppercase tracking-wide text-charcoal/50">
          {t("Resource limits")}
        </th>
      </tr>
      {LIMITS.map(([key, label]) => {
        const metric = usage.find((row) => row.key === key);
        return (
          <tr key={key} className="border-t border-line">
            <th className="sticky start-0 bg-white px-4 py-2 text-start font-medium dark:bg-zinc-900">{t(label)}</th>
            {plans.map((plan) => {
              const cell = planLimitCell(plan, key);
              const showUse = plan.code === currentCode && metric?.state === "known" && metric.used !== null;
              return (
                <td key={plan.code} className={`px-3 py-2 tabular-nums ${plan.code === currentCode ? "bg-accent/5" : ""}`}>
                  {cell.state === "configured" ? cell.value : cell.state === "unlimited" ? t("Unlimited") : t("Not configured")}
                  {showUse ? <span className="mt-1 block text-xs text-charcoal/60 dark:text-white/60">{t("{count} in use", { count: metric.used ?? 0 })}</span> : null}
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
