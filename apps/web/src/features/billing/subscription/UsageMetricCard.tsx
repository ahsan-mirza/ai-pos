import { useLocale } from "@ai-pos/ui";
import { remainingCapacity, type UsageMetricView } from "./display";

export function UsageProgress({ used, limit, tone = "neutral" }: { used: number; limit: number; tone?: "neutral" | "warning" | "limit" }) {
  const width = limit <= 0 ? 0 : Math.min(100, Math.round((used / limit) * 100));
  const bar = tone === "limit" ? "bg-red-600" : tone === "warning" ? "bg-amber-500" : "bg-accent";
  return (
    <div
      className="h-1.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={limit}
      aria-valuenow={Math.min(used, limit)}
    >
      <div className={`h-full rounded-full ${bar}`} style={{ width: `${width}%` }} />
    </div>
  );
}

/** Shows a real cap. A missing usage count stays unavailable instead of a fabricated bar. */
export function UsageMetricCard({ metric }: { metric: UsageMetricView }) {
  const { t } = useLocale();
  const remaining = remainingCapacity(metric);
  return (
    <article className="rounded-2xl border border-line bg-white p-3 dark:border-zinc-800 dark:bg-zinc-900">
      <h3 className="text-sm font-semibold text-charcoal dark:text-white">{t(metric.label)}</h3>
      {metric.state === "known" && metric.used !== null && metric.limit !== null ? (
        <div className="mt-2 grid gap-2">
          <p className="text-sm tabular-nums text-charcoal/80 dark:text-white/80" dir="ltr">
            {t("{used} of {limit}", { used: metric.used, limit: metric.limit })}
          </p>
          <UsageProgress used={metric.used} limit={metric.limit} tone={metric.tone} />
          {metric.tone === "limit" ? (
            <p className="text-xs font-semibold text-red-800 dark:text-red-300">{t("Limit reached")}</p>
          ) : metric.tone === "warning" ? (
            <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">{t("Near the plan limit")}</p>
          ) : remaining !== null ? (
            <p className="text-xs text-charcoal/55 dark:text-white/55">{t("{count} remaining", { count: remaining })}</p>
          ) : null}
        </div>
      ) : null}
      {metric.state === "unavailable" ? (
        <div className="mt-2 grid gap-1">
          {metric.limit !== null ? (
            <p className="text-sm tabular-nums text-charcoal dark:text-white">
              {t("Allowed")}: <span dir="ltr">{metric.limit}</span>
            </p>
          ) : null}
          <p className="text-xs text-charcoal/55 dark:text-white/55">{t("Usage unavailable")}</p>
        </div>
      ) : null}
      {metric.state === "unlimited" ? (
        <p className="mt-2 text-sm text-charcoal/80 dark:text-white/80" dir="ltr">
          {metric.used !== null ? t("{count} · Unlimited", { count: metric.used }) : t("Unlimited")}
        </p>
      ) : null}
      {metric.state === "unconfigured" ? (
        <div className="mt-2 grid gap-1">
          {metric.used !== null ? (
            <p className="text-sm tabular-nums text-charcoal dark:text-white" dir="ltr">
              {metric.used}
            </p>
          ) : null}
          <p className="text-xs text-charcoal/55 dark:text-white/55">{t("Not configured")}</p>
        </div>
      ) : null}
      {metric.state === "zero" ? <p className="mt-2 text-sm text-charcoal/80 dark:text-white/80">{t("Zero capacity")}</p> : null}
    </article>
  );
}
