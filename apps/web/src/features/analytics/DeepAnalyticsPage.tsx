import { formatMoney, type DeepKpi, type DeepOverview } from "@ai-pos/shared-types";
import { colors } from "@ai-pos/design-tokens";
import { Download, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { HorizontalBars, Sparkline } from "../../components/charts/Charts";
import { ErrorNote, GhostButton, TextField } from "../../components/ui/Field";
import { apiBlob, apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

const iso = (value: Date) => value.toISOString().slice(0, 10);

function moneyOf(cents: number | null, currency: string): string {
  return cents === null ? "—" : formatMoney(cents, currency);
}

function kpiValue(kpi: DeepKpi, currency: string): string {
  if (kpi.quality === "unavailable") return "—";
  if (kpi.bps !== null) return `${(kpi.bps / 100).toFixed(1)}%`;
  if (kpi.count !== null) return kpi.count.toLocaleString();
  return moneyOf(kpi.cents, currency);
}

function KpiCard({ kpi, currency }: { kpi: DeepKpi; currency: string }) {
  return (
    <article className="flex min-h-36 flex-col rounded-card border border-line bg-white p-5">
      <p className="text-sm text-charcoal/60">{kpi.label}</p>
      <p className="mt-3 text-2xl font-semibold tabular-nums">{kpiValue(kpi, currency)}</p>
      <p className="mt-2 text-xs leading-5 text-charcoal/55">{kpi.definition}</p>
      {kpi.note ? <p className="mt-1 text-xs text-accent">{kpi.note}</p> : null}
    </article>
  );
}

export function DeepAnalyticsPage() {
  const { user } = useAuth();
  const { stores } = useStores();
  const [from, setFrom] = useState(() => iso(new Date(Date.now() - 29 * 24 * 60 * 60 * 1000)));
  const [to, setTo] = useState(() => iso(new Date()));
  const [compare, setCompare] = useState(false);
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [report, setReport] = useState<DeepOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const branch = storeId ? `&store_id=${storeId}` : "";
    const query = `from=${from}&to=${to}&compare=${compare ? "true" : "false"}${branch}`;
    try {
      setReport(await apiGet<DeepOverview>(`/api/v1/deep-analytics/overview?${query}`));
    } catch (caught) {
      setReport(null);
      setError(errorMessage(caught, "Deep Analytics could not be loaded."));
    } finally {
      setLoading(false);
    }
  }, [compare, from, storeId, to]);

  useEffect(() => {
    void load();
  }, [load]);

  async function download() {
    setExporting(true);
    setError(null);
    const branch = storeId ? `&store_id=${storeId}` : "";
    try {
      const blob = await apiBlob(`/api/v1/deep-analytics/export?from=${from}&to=${to}&compare=${compare}${branch}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "deep-analytics.csv";
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(errorMessage(caught, "The export could not be downloaded."));
    } finally {
      setExporting(false);
    }
  }

  const currency = report?.currency ?? "AED";
  const branchName = stores.find((store) => store.id === storeId)?.name ?? (storeId ? "This branch" : "All branches");
  const updated = report ? new Date(report.generated_at).toLocaleString() : "";

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Deep Analytics</h1>
          <p className="mt-1 text-sm text-charcoal/60">
            {branchName}
            {updated ? ` · Updated ${updated}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
          <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          {user?.store_id ? null : (
            <label className="text-sm font-medium">
              Branch
              <select
                className="mt-1.5 block h-11 rounded-xl border border-line bg-white px-3"
                value={storeId}
                onChange={(event) => setStoreId(event.target.value)}
              >
                <option value="">All branches</option>
                {storeOptions(stores).map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="flex h-11 items-center gap-2 text-sm">
            <input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} />
            Compare with previous period
          </label>
          <GhostButton type="button" onClick={() => void load()} disabled={loading}>
            <RefreshCw className="mr-2 h-4 w-4" aria-hidden="true" />
            Refresh
          </GhostButton>
          <GhostButton type="button" onClick={() => void download()} disabled={exporting || !report}>
            <Download className="mr-2 h-4 w-4" aria-hidden="true" />
            Export
          </GhostButton>
        </div>
      </header>

      <ErrorNote message={error} />
      {report ? <p className="text-sm text-charcoal/60">{report.coverage}</p> : null}

      {loading && !report ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true">
          {Array.from({ length: 8 }, (_, index) => (
            <div key={index} className="h-36 animate-pulse rounded-card bg-surface" />
          ))}
        </div>
      ) : null}

      {report ? (
        <>
          <section className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {report.kpis.map((kpi) => (
              <KpiCard key={kpi.key} kpi={kpi} currency={currency} />
            ))}
          </section>

          {report.comparison ? (
            <p className="text-sm text-charcoal/70">
              Previous period {report.comparison.period_from} to {report.comparison.period_to}: revenue{" "}
              {moneyOf(report.comparison.revenue_cents, currency)}
              {report.comparison.revenue_growth_bps === null
                ? " (no earlier revenue to compare)."
                : `, ${(report.comparison.revenue_growth_bps / 100).toFixed(1)}% versus that period.`}
            </p>
          ) : null}

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Revenue trend</h2>
              <div className="mt-4">
                {report.trend.some((point) => point.revenue_cents !== 0) ? (
                  <Sparkline values={report.trend.map((point) => point.revenue_cents)} stroke={colors.accent} />
                ) : (
                  <p className="text-sm text-charcoal/60">No posted sales in this period.</p>
                )}
              </div>
            </article>
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Gross profit trend</h2>
              <div className="mt-4">
                {report.trend.some((point) => point.gross_profit_cents !== 0) ? (
                  <Sparkline values={report.trend.map((point) => point.gross_profit_cents)} stroke={colors.charcoal} />
                ) : (
                  <p className="text-sm text-charcoal/60">No profit movement in this period.</p>
                )}
              </div>
            </article>
          </section>

          {report.hourly.length > 0 ? (
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Sales by hour</h2>
              <p className="mt-1 text-xs text-charcoal/50">Net sales, excluding VAT, grouped by the hour on each posted sale.</p>
              <div className="mt-4">
                {report.hourly.some((point) => point.revenue_cents !== 0) ? (
                  <HorizontalBars
                    rows={report.hourly
                      .filter((point) => point.revenue_cents !== 0)
                      .map((point) => ({
                        label: `${String(point.hour).padStart(2, "0")}:00`,
                        value: point.revenue_cents,
                        display: moneyOf(point.revenue_cents, currency),
                      }))}
                  />
                ) : (
                  <p className="text-sm text-charcoal/60">No posted sales in these hours.</p>
                )}
              </div>
            </article>
          ) : report.hourly_note ? (
            <p className="text-sm text-charcoal/60">{report.hourly_note}</p>
          ) : null}

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Sales by category</h2>
              <div className="mt-4">
                {report.categories.length === 0 ? (
                  <p className="text-sm text-charcoal/60">No category sales in this period.</p>
                ) : (
                  <HorizontalBars
                    rows={report.categories.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                )}
              </div>
            </article>
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Payment methods</h2>
              <p className="mt-1 text-xs text-charcoal/50">{report.payments_note}</p>
              <div className="mt-4">
                {report.payments.length === 0 ? (
                  <p className="text-sm text-charcoal/60">No tenders in this period.</p>
                ) : (
                  <HorizontalBars
                    rows={report.payments.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                )}
              </div>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Top products</h2>
              <div className="mt-4">
                {report.products.length === 0 ? (
                  <p className="text-sm text-charcoal/60">No product sales in this period.</p>
                ) : (
                  <HorizontalBars
                    rows={report.products.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                )}
              </div>
            </article>
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Lowest product sales</h2>
              <div className="mt-4">
                {report.slow_products.length === 0 ? (
                  <p className="text-sm text-charcoal/60">Shown when more products sold than the top list.</p>
                ) : (
                  <HorizontalBars
                    rows={report.slow_products.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                )}
              </div>
            </article>
          </section>

          <section className="grid gap-4 lg:grid-cols-2">
            <article className="rounded-card border border-line bg-white p-5">
              <h2 className="text-sm font-medium text-charcoal/70">Cashiers</h2>
              <p className="mt-1 text-xs text-charcoal/50">Net sales, excluding VAT, on sales each person rang up.</p>
              <div className="mt-4">
                {report.cashiers.length === 0 ? (
                  <p className="text-sm text-charcoal/60">No cashier sales in this period.</p>
                ) : (
                  <HorizontalBars
                    rows={report.cashiers.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                )}
              </div>
            </article>
            {report.branches.length > 1 ? (
              <article className="rounded-card border border-line bg-white p-5">
                <h2 className="text-sm font-medium text-charcoal/70">Branches</h2>
                <div className="mt-4">
                  <HorizontalBars
                    rows={report.branches.map((row) => ({
                      label: row.name,
                      value: row.cents,
                      display: moneyOf(row.cents, currency),
                    }))}
                  />
                </div>
              </article>
            ) : null}
          </section>

          {report.sections.length > 0 ? (
            <section className="grid gap-4 sm:grid-cols-2">
              {report.sections.map((section) => (
                <article key={section.id} className="rounded-card border border-line bg-white p-5">
                  <h2 className="text-sm font-medium">{section.label}</h2>
                  <p className="mt-2 text-sm text-charcoal/70">{section.detail}</p>
                  {section.cents !== null ? (
                    <p className="mt-3 text-xl font-semibold tabular-nums">{moneyOf(section.cents, currency)}</p>
                  ) : null}
                  {section.status === "unavailable" ? (
                    <p className="mt-2 text-xs font-medium text-charcoal/45">Not available for this business</p>
                  ) : null}
                </article>
              ))}
            </section>
          ) : null}

          <article className="rounded-card border border-line bg-white p-5">
            <h2 className="text-sm font-medium">Forecast</h2>
            <p className="mt-2 text-sm text-charcoal/70">{report.forecast.note}</p>
            {report.forecast.status === "estimated" && report.forecast.daily_revenue_cents !== null ? (
              <p className="mt-3 text-sm">
                Estimated daily revenue {moneyOf(report.forecast.daily_revenue_cents, currency)} over{" "}
                {report.forecast.horizon_days} days. This is an estimate, not a recorded result.
              </p>
            ) : null}
          </article>
        </>
      ) : null}
    </div>
  );
}
