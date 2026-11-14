import { formatMoney, type BillingPlan } from "@ai-pos/shared-types";
import { formatDate, formatDateTime, useLocale } from "@ai-pos/ui";
import { isCustomPlan, isLegacyPlanCode, planLimits } from "../subscriptionPlans";
import { aiAllowanceView, capabilityGroups, presentUsage, upgradeRecommendation, usageMetricViews, type UsagePayload } from "./display";
import { ErrorState, LoadingCards } from "./States";
import { SubscriptionStatus } from "./SubscriptionStatus";
import { UsageMetricCard } from "./UsageMetricCard";

interface SubscriptionRecord {
  plan_name: string;
  plan_code: string;
  status: string;
  cycle_name: string;
  price_fils?: number;
  currency?: string;
  current_period_end?: string | null;
  trial_ends_at?: string | null;
}

function shownDate(value: string): string {
  return formatDate(value) || value.slice(0, 10);
}

export function SubscriptionSummaryCard({
  subscription,
  plan,
  usage,
  usageError,
  onRetryUsage,
  features,
  purchased = [],
  plans = [],
  onUpgrade,
  accessState,
  attentionLabel,
  trial,
}: {
  subscription: SubscriptionRecord | null;
  plan: BillingPlan | undefined;
  /** Undefined while the usage request is in flight. Null after it failed. */
  usage?: UsagePayload | null;
  usageError?: string | null;
  onRetryUsage?: () => void;
  features?: Array<{ feature_key: string; label: string; state: string }> | null;
  purchased?: Array<{ name: string; keys: string[] }>;
  plans?: BillingPlan[];
  onUpgrade?: (plan: BillingPlan) => void;
  accessState?: string | null;
  attentionLabel?: string | null;
  trial?: { status: string; capabilities: string[]; days_remaining: number | null; expires_at: string | null } | null;
}) {
  const { t } = useLocale();
  const metrics = usage ? presentUsage(usage) : usageMetricViews(plan);
  const allowance = aiAllowanceView(plan);
  const history = planLimits(plan).find((row) => row.key === "sales_history_days");

  if (!subscription) {
    return <p className="text-sm text-charcoal/70 dark:text-white/70">{t("No subscription is assigned yet.")}</p>;
  }

  const price =
    typeof subscription.price_fils === "number"
      ? t("{price} · {cycle}", {
          price: formatMoney(subscription.price_fils, subscription.currency || "AED"),
          cycle: t(subscription.cycle_name),
        })
      : t(subscription.cycle_name);
  const recommendation = usage ? upgradeRecommendation(metrics, plans, subscription.plan_code) : null;
  const purchasedKeys = new Set(purchased.flatMap((item) => item.keys));
  const groups = features ? capabilityGroups(features, purchasedKeys, purchased.map((item) => item.name)) : null;

  return (
    <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{t("Current plan")}</p>
          <h2 className="mt-1 text-2xl font-semibold text-charcoal dark:text-white">{t(subscription.plan_name)}</h2>
          <p className="mt-1 text-sm text-charcoal/80 dark:text-white/80" dir="ltr">
            {price}
          </p>
          <p className="mt-3 max-w-xl text-sm text-charcoal/80 dark:text-white/80">
            {subscription.plan_code === "FREE"
              ? t("Your business is running on the Free plan. Upgrade whenever you need more capabilities.")
              : t("Your business is on {plan}.", { plan: subscription.plan_name })}
          </p>
          {isLegacyPlanCode(subscription.plan_code) ? (
            <p className="mt-3 max-w-xl text-sm text-charcoal/80 dark:text-white/80">
              {t("This package is retired. The subscription stays on {plan} until a move to Free, Growth, Pro AI, or Enterprise is agreed.", {
                plan: subscription.plan_name,
              })}
            </p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {attentionLabel ? <span className="text-xs font-semibold text-amber-900 dark:text-amber-200">{t(attentionLabel)}</span> : null}
          <SubscriptionStatus status={subscription.status} />
          {accessState === "grace" || accessState === "restricted" ? (
            <span className="text-xs font-semibold text-charcoal/70 dark:text-white/70">{t(accessState === "grace" ? "Grace period" : "Restricted")}</span>
          ) : null}
          {trial?.status === "active" ? (
            <span className="text-xs font-semibold text-charcoal/70 dark:text-white/70">{t("Pro AI trial")}</span>
          ) : null}
          {trial?.status === "expired" ? (
            <span className="text-xs font-semibold text-charcoal/70 dark:text-white/70">{t("Trial expired")}</span>
          ) : null}
        </div>
      </div>
      <dl className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="rounded-2xl bg-zinc-50 px-3 py-2 dark:bg-white/5">
          <dt className="text-xs text-charcoal/50">{t("Billing cycle")}</dt>
          <dd className="mt-0.5 text-sm font-semibold">{t(subscription.cycle_name)}</dd>
        </div>
        {subscription.current_period_end ? (
          <div className="rounded-2xl bg-zinc-50 px-3 py-2 dark:bg-white/5">
            <dt className="text-xs text-charcoal/50">{t("Next renewal")}</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums" dir="ltr">
              {shownDate(subscription.current_period_end)}
            </dd>
          </div>
        ) : null}
        {subscription.trial_ends_at ? (
          <div className="rounded-2xl bg-zinc-50 px-3 py-2 dark:bg-white/5">
            <dt className="text-xs text-charcoal/50">{t("Trial ends")}</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums" dir="ltr">
              {shownDate(subscription.trial_ends_at)}
            </dd>
          </div>
        ) : null}
        {history ? (
          <div className="rounded-2xl bg-zinc-50 px-3 py-2 dark:bg-white/5">
            <dt className="text-xs text-charcoal/50">{t("Sales history")}</dt>
            <dd className="mt-0.5 text-sm font-semibold tabular-nums">{t("{count} days", { count: history.value })}</dd>
          </div>
        ) : null}
      </dl>
      <div className="flex flex-wrap gap-3 text-sm font-semibold">
        <a href="#plans" className="text-accent">
          {t("Explore plans")}
        </a>
        <a href="#billing" className="text-accent">
          {t("Billing")}
        </a>
      </div>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold text-charcoal dark:text-white">{t("Resource usage")}</h3>
          {onRetryUsage ? (
            <button type="button" className="text-sm font-semibold text-accent" onClick={onRetryUsage}>
              {t("Refresh usage")}
            </button>
          ) : null}
        </div>
        {usage === undefined && usageError == null ? <LoadingCards count={5} /> : null}
        {usage === null ? <ErrorState message={t(usageError ?? "Could not load usage.")} onRetry={onRetryUsage} /> : null}
        {usage ? (
          <>
            <p className="text-xs text-charcoal/50 dark:text-white/50">
              {t("Usage measured {when}", { when: formatDateTime(usage.measured_at) })}
            </p>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
              {metrics.map((metric) => (
                <UsageMetricCard key={metric.key} metric={metric} />
              ))}
            </div>
          </>
        ) : null}
      </div>
      {recommendation ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line px-3 py-3 dark:border-zinc-800">
          <p className="text-sm text-charcoal/80 dark:text-white/80">
            {recommendation.contact
              ? t("{plan} can be arranged when {metric} needs more room. Contact sales.", {
                  plan: t(recommendation.plan.name),
                  metric: t(recommendation.metric),
                })
              : t("{plan} includes a higher {metric} allowance.", {
                  plan: t(recommendation.plan.name),
                  metric: t(recommendation.metric),
                })}
          </p>
          {recommendation.contact || isCustomPlan(recommendation.plan) ? (
            <a href={`#plan-${recommendation.plan.code}`} className="text-sm font-semibold text-accent">
              {t("Contact sales")}
            </a>
          ) : (
            <button type="button" className="text-sm font-semibold text-accent" onClick={() => onUpgrade?.(recommendation.plan)}>
              {t("Review {plan}", { plan: t(recommendation.plan.name) })}
            </button>
          )}
        </div>
      ) : null}
      {groups ? (
        <div className="grid gap-3">
          <h3 className="text-sm font-semibold text-charcoal dark:text-white">{t("Capabilities")}</h3>
          <CapabilityList title={t("Included")} items={groups.included} />
          <CapabilityList title={t("Purchased")} items={groups.purchased} />
          <CapabilityList title={t("Trial")} items={groups.trial} />
          <CapabilityList title={t("Unavailable")} items={groups.unavailable} />
        </div>
      ) : null}
      {allowance.state === "configured" ? (
        <p className="text-sm text-charcoal/70 dark:text-white/70">
          <span className="font-semibold text-charcoal dark:text-white">{t("AI allowance")}: </span>
          {t("{count} per month", { count: allowance.value })}. {t("Configured allowance. Usage is not counted on this page.")}
        </p>
      ) : null}
      {allowance.state === "unlimited" ? (
        <p className="text-sm text-charcoal/70 dark:text-white/70">
          <span className="font-semibold text-charcoal dark:text-white">{t("AI allowance")}: </span>
          {t("Unlimited")}. {t("Configured allowance. Usage is not counted on this page.")}
        </p>
      ) : null}
    </div>
  );
}

function CapabilityList({ title, items }: { title: string; items: string[] }) {
  const { t } = useLocale();
  if (items.length === 0) return null;
  return (
    <div className="min-w-0">
      <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{title}</p>
      <ul className="mt-1 flex flex-wrap gap-2">
        {items.map((item) => (
          <li key={item} className="rounded-full bg-zinc-100 px-2.5 py-1 text-xs text-charcoal dark:bg-white/10 dark:text-white">
            {t(item)}
          </li>
        ))}
      </ul>
    </div>
  );
}
