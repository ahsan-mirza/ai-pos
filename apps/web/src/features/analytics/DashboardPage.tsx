import { AnalyticsTimeframe, formatMoney, type AnalyticsSummary } from "@ai-pos/shared-types";
import { useLocale } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { BarSeries, CategoryDonut, HorizontalBars, Sparkline, SplitBar } from "../../components/charts/Charts";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiGet } from "../../lib/api";
import { useCurrency } from "../../lib/currency";

function formatGrowth(bps: number): string {
  const value = bps / 100;
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(1)}%`;
}

export function DashboardPage() {
  const { currency } = useCurrency();
  const { t } = useLocale();
  const options = [
    { value: AnalyticsTimeframe.AllTime, label: t("All time") },
    { value: AnalyticsTimeframe.Daily, label: t("Daily") },
    { value: AnalyticsTimeframe.Weekly, label: t("Weekly") },
    { value: AnalyticsTimeframe.Monthly, label: t("Monthly") },
  ] as const;
  const [timeframe, setTimeframe] = useState<AnalyticsTimeframe>(AnalyticsTimeframe.AllTime);
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const path = `/api/v1/analytics/summary?timeframe=${timeframe}&currency=${currency}`;
    apiGet<AnalyticsSummary>(path)
      .then((live) => {
        if (!controller.signal.aborted) {
          setSummary(live);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => controller.abort();
  }, [timeframe, currency]);

  if (summary === null) {
    return (
      <section className="space-y-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="font-sans text-[28px] font-semibold leading-tight tracking-tight md:text-[32px]">
              {t("Retail Inventory")}
            </h2>
            <p className="mt-1 text-sm text-charcoal/60">
              {failed ? t("Totals could not be loaded.") : t("Loading totals…")}
            </p>
          </div>
          <SegmentedControl label={t("Timeframe")} value={timeframe} options={options} onChange={setTimeframe} />
        </div>
      </section>
    );
  }

  const split = summary.payment_split.slice(0, 2).map((item, index) => ({
    label: item.method.replace("_", " "),
    amount: item.revenue_cents,
    color: index === 0 ? "#FFFFFF" : "#222026",
  }));
  const orders =
    summary.average_ticket_cents > 0 ? Math.round(summary.net_revenue_cents / summary.average_ticket_cents) : 0;

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="font-sans text-[28px] font-semibold leading-tight tracking-tight md:text-[32px]">
            {t("Retail Inventory")}
          </h2>
          <p className="mt-1 text-sm text-charcoal/60">{t("Completed sales in {currency}.", { currency: summary.currency })}</p>
        </div>
        <SegmentedControl label={t("Timeframe")} value={timeframe} options={options} onChange={setTimeframe} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:gap-6">
        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl bg-charcoal p-6 text-white">
          <div>
            <p className="text-sm font-medium text-white/60">{t("Net revenue")}</p>
            <p className="mt-3 break-words font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums xl:text-[40px]">
              {formatMoney(summary.net_revenue_cents, summary.currency)}
            </p>
            <p className="mt-2 text-sm text-white/60">
              {t("{count} total orders", { count: orders.toLocaleString() })}
            </p>
          </div>
          <Sparkline values={summary.revenue_series} stroke="#FFFFFF" />
        </article>

        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl bg-accent p-6 text-white">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-white/80">{t("Units sold")}</p>
              <p className="mt-3 font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums xl:text-[40px]">
                {summary.units_sold.toLocaleString()}
              </p>
            </div>
            <span className="shrink-0 rounded-full bg-white/20 px-3 py-1.5 text-xs font-semibold tabular-nums text-white">
              {summary.units_growth_bps === null ? t("No prior period") : formatGrowth(summary.units_growth_bps)}
            </span>
          </div>
          <SplitBar segments={split.length > 0 ? split : [{ label: t("No tenders"), amount: 0, color: "#FFFFFF" }]} />
        </article>

        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl border border-line bg-white p-6">
          <div>
            <p className="text-sm font-medium text-charcoal/60">{t("Average ticket")}</p>
            <p className="mt-3 font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums text-charcoal xl:text-[40px]">
              {formatMoney(summary.average_ticket_cents, summary.currency)}
            </p>
          </div>
          <BarSeries values={summary.revenue_series} />
        </article>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 lg:gap-6">
        <article className="rounded-2xl border border-line bg-white p-6">
          <h3 className="mb-6 font-sans text-lg font-semibold">{t("Category mix")}</h3>
          <CategoryDonut slices={summary.categories.map((item) => ({ label: item.category, value: item.units }))} />
        </article>
        <article className="rounded-2xl border border-line bg-white p-6">
          <h3 className="mb-6 font-sans text-lg font-semibold">{t("Revenue by category")}</h3>
          <HorizontalBars
            rows={summary.categories.map((item) => ({
              label: item.category,
              value: item.revenue_cents,
              display: formatMoney(item.revenue_cents, summary.currency),
            }))}
          />
        </article>
      </div>
    </section>
  );
}
