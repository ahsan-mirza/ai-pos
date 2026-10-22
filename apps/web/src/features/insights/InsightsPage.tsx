import {
  ANOMALY_LABELS,
  Capability,
  PRICE_ACTION_LABELS,
  Permission,
  formatMoney,
  formatWeight,
  type AnomalyReport,
  type PriceAction,
  type PriceSuggestion,
  type PricingReport,
  type ShrinkReport,
  type ShrinkSlice,
} from "@ai-pos/shared-types";
import { Armchair, ChefHat, Radar, ShieldAlert, Sparkles, Tags, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { apiGet, apiPatch } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCapabilities } from "../../lib/capabilities";
import { errorMessage } from "../users/api";
import { KitchenTab, TablesTab, UpsellTab } from "./RestaurantTabs";

type Tab = "anomalies" | "pricing" | "shrink" | "kitchen" | "tables" | "upsell";

const TABS: { id: Tab; label: string; icon: typeof Radar; permission: Permission; capability?: Capability }[] = [
  { id: "anomalies", label: "Unusual activity", icon: ShieldAlert, permission: Permission.AuditRead },
  { id: "pricing", label: "Price suggestions", icon: Tags, permission: Permission.PortalReportsRead },
  { id: "shrink", label: "Shrink", icon: Trash2, permission: Permission.PortalReportsRead },
  { id: "kitchen", label: "Kitchen", icon: ChefHat, permission: Permission.PortalReportsRead, capability: Capability.Kds },
  { id: "tables", label: "Tables", icon: Armchair, permission: Permission.PortalReportsRead, capability: Capability.Tables },
  { id: "upsell", label: "Upsells", icon: Sparkles, permission: Permission.PortalReportsRead },
];

const severityStyle = {
  HIGH: "bg-red-50 text-red-700 ring-red-200",
  MEDIUM: "bg-amber-50 text-amber-800 ring-amber-200",
} as const;

const pct = (bps: number) => `${(bps / 100).toFixed(1)}%`;

/** Statistical insights from the ledgers: who stands out, which prices to change, where stock goes missing. */
export function InsightsPage() {
  const { can } = useAuth();
  const { has } = useCapabilities();
  const [params, setParams] = useSearchParams();
  const tabs = TABS.filter((tab) => can(tab.permission) && (tab.capability === undefined || has(tab.capability)));
  const requested = params.get("tab") as Tab | null;
  const tab = tabs.find((item) => item.id === requested)?.id ?? tabs[0]?.id ?? "pricing";

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <Radar size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">AI insights</h2>
            <p className="text-sm text-charcoal/60">
              Signals worked out from your sales, refunds, audit trail, shifts and stock movements. Each one says why
              it fired, so you can check it before acting.
            </p>
          </div>
        </div>
        <div role="tablist" aria-label="Insights" className="mt-5 flex flex-wrap gap-2">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setParams({ tab: item.id })}
              className={`inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-semibold transition ${
                tab === item.id ? "bg-charcoal text-white" : "bg-surface text-charcoal/70 hover:text-charcoal"
              }`}
            >
              <item.icon size={15} aria-hidden="true" /> {item.label}
            </button>
          ))}
        </div>
      </div>
      {tab === "anomalies" ? <AnomaliesTab /> : null}
      {tab === "pricing" ? <PricingTab canApply={can(Permission.PortalInventoryManage)} /> : null}
      {tab === "shrink" ? <ShrinkTab /> : null}
      {tab === "kitchen" ? <KitchenTab /> : null}
      {tab === "tables" ? <TablesTab /> : null}
      {tab === "upsell" ? <UpsellTab /> : null}
    </section>
  );
}

function useReport<T>(path: string, failure: string) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setData(await apiGet<T>(path));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, failure));
    }
  }, [path, failure]);
  useEffect(() => {
    void load();
  }, [load]);
  return { data, error, reload: load };
}

function DaysPicker({ value, options, onChange }: { value: number; options: number[]; onChange: (days: number) => void }) {
  return (
    <div className="flex items-center gap-1 rounded-full bg-surface p-1 text-xs font-semibold">
      {options.map((days) => (
        <button
          key={days}
          type="button"
          aria-pressed={value === days}
          onClick={() => onChange(days)}
          className={`rounded-full px-3 py-1.5 ${value === days ? "bg-white shadow-sm" : "text-charcoal/60"}`}
        >
          {days} days
        </button>
      ))}
    </div>
  );
}

function AnomaliesTab() {
  const [days, setDays] = useState(30);
  const { data, error } = useReport<AnomalyReport>(`/api/v1/insights/anomalies?days=${days}`, "Could not load activity.");
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  const money = (cents: number) => formatMoney(cents, data.currency);
  return (
    <>
      <article className="rounded-card border border-line bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-base font-semibold">Signals</h3>
            <p className="text-xs text-charcoal/60">
              {data.peers > 3
                ? `Each cashier is compared with the ${data.peers - 1} others who rang at least 10 sales (median and spread), so a busy store does not flag everyone.`
                : "Too few cashiers with 10+ sales to compare with each other, so fixed limits apply (for example 5 voids per 100 sales)."}{" "}
              Drawers are checked shift by shift.
            </p>
          </div>
          <DaysPicker value={days} options={[7, 30, 90]} onChange={setDays} />
        </div>
        {data.anomalies.length === 0 ? (
          <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">Nothing unusual in the last {data.days} days.</p>
        ) : (
          <ul className="mt-4 space-y-2">
            {data.anomalies.map((item, index) => (
              <li key={`${item.user_id}-${item.kind}-${index}`} className="flex flex-wrap items-start gap-3 rounded-2xl border border-line p-4">
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ring-1 ${severityStyle[item.severity]}`}>
                  {item.severity === "HIGH" ? "High" : "Medium"}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold">
                    {ANOMALY_LABELS[item.kind]} · {item.user_name}
                  </p>
                  <p className="mt-0.5 text-sm text-charcoal/70">{item.summary}</p>
                </div>
                <Link to="/audit" className="text-xs font-semibold text-accent hover:underline">
                  Audit trail
                </Link>
              </li>
            ))}
          </ul>
        )}
      </article>
      <article className="overflow-x-auto rounded-card border border-line bg-white p-5">
        <h3 className="text-base font-semibold">Activity by cashier</h3>
        <table className="mt-3 w-full min-w-[820px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Cashier</th>
              <th className="pb-2 text-right font-medium">Sales</th>
              <th className="pb-2 text-right font-medium">Voids</th>
              <th className="pb-2 text-right font-medium">No-sale opens</th>
              <th className="pb-2 text-right font-medium">Refunds</th>
              <th className="pb-2 text-right font-medium">Price overrides</th>
              <th className="pb-2 text-right font-medium">Shifts</th>
              <th className="pb-2 text-right font-medium">Short / over</th>
            </tr>
          </thead>
          <tbody>
            {data.staff.map((row) => (
              <tr key={row.user_id} className="border-t border-line">
                <td className="py-2 font-medium">{row.user_name}</td>
                <td className="py-2 text-right tabular-nums">{row.sales}</td>
                <td className="py-2 text-right tabular-nums">{row.voids}</td>
                <td className="py-2 text-right tabular-nums">{row.no_sales}</td>
                <td className="py-2 text-right tabular-nums">
                  {row.refunds} · {money(row.refund_cents)}
                </td>
                <td className="py-2 text-right tabular-nums">{row.price_overrides}</td>
                <td className="py-2 text-right tabular-nums">{row.shifts_closed}</td>
                <td className="py-2 text-right tabular-nums">
                  {money(row.cash_short_cents)} / {money(row.cash_over_cents)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </>
  );
}

function PricingTab({ canApply }: { canApply: boolean }) {
  const confirm = useConfirm();
  const { data, error, reload } = useReport<PricingReport>("/api/v1/insights/pricing?limit=200", "Could not load suggestions.");
  const [filter, setFilter] = useState<PriceAction | "ALL">("ALL");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<string | null>(null);
  const rows = useMemo(
    () => (data ? data.suggestions.filter((row) => filter === "ALL" || row.action === filter) : []),
    [data, filter],
  );
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  const money = (cents: number) => formatMoney(cents, data.currency);

  const apply = async (row: PriceSuggestion) => {
    const label = `${money(row.price_cents)} → ${money(row.suggested_price_cents)}`;
    const accepted = await confirm({
      title: "Change price",
      message: `Change ${row.name} from ${label}${row.sold_by_weight ? " per kg" : ""} at every branch?`,
      confirmLabel: "Change price",
    });
    if (!accepted) return;
    setBusy(`${row.product_id}-${row.action}`);
    setFailure(null);
    try {
      await apiPatch(`/api/v1/products/${row.product_id}`, { price_cents: row.suggested_price_cents });
      setNotice(`${row.name} now sells at ${money(row.suggested_price_cents)}. Print new shelf labels from Inventory.`);
      await reload();
    } catch (caught) {
      setFailure(errorMessage(caught, "Could not change the price."));
    } finally {
      setBusy(null);
    }
  };

  const actions = Object.keys(PRICE_ACTION_LABELS) as PriceAction[];
  return (
    <article className="rounded-card border border-line bg-white p-5">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-pressed={filter === "ALL"}
          onClick={() => setFilter("ALL")}
          className={`rounded-full px-3 py-1.5 text-xs font-semibold ${filter === "ALL" ? "bg-charcoal text-white" : "bg-surface"}`}
        >
          All · {data.suggestions.length}
        </button>
        {actions.map((action) => (
          <button
            key={action}
            type="button"
            aria-pressed={filter === action}
            onClick={() => setFilter(action)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold ${filter === action ? "bg-charcoal text-white" : "bg-surface"}`}
          >
            {PRICE_ACTION_LABELS[action]} · {data.counts[action] ?? 0}
          </button>
        ))}
      </div>
      <p className="mt-3 text-xs text-charcoal/60">
        Prices are chain-wide. Rises respect demand and margin floors; markdowns never go under cost except for stock
        that would otherwise expire.
      </p>
      {notice ? <p role="status" className="mt-3 rounded-2xl bg-surface px-4 py-3 text-sm">{notice}</p> : null}
      <ErrorNote message={failure} />
      {rows.length === 0 ? (
        <p className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">No price changes to suggest right now.</p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[900px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Product</th>
                <th className="pb-2 font-medium">Why</th>
                <th className="pb-2 text-right font-medium">Now</th>
                <th className="pb-2 pl-6 text-right font-medium">Suggested</th>
                <th className="pb-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const key = `${row.product_id}-${row.action}`;
                return (
                  <tr key={key} className="border-t border-line align-top">
                    <td className="py-3 pr-4">
                      <span className="block font-medium">{row.name}</span>
                      <span className="block font-mono text-[11px] text-charcoal/50">
                        {row.sku}
                        {row.store_code ? ` · ${row.store_code}` : ""}
                      </span>
                      <span className="mt-1 inline-block rounded-full bg-surface px-2 py-0.5 text-[11px] font-semibold">
                        {PRICE_ACTION_LABELS[row.action]}
                      </span>
                    </td>
                    <td className="max-w-md py-3 pr-4 text-charcoal/70">{row.reason}</td>
                    <td className="py-3 text-right tabular-nums">
                      {money(row.price_cents)}
                      {row.sold_by_weight ? "/kg" : ""}
                    </td>
                    <td className="py-3 text-right font-semibold tabular-nums">
                      {money(row.suggested_price_cents)}
                      <span className={`block text-xs ${row.change_pct < 0 ? "text-red-600" : "text-emerald-700"}`}>
                        {row.change_pct > 0 ? "+" : ""}
                        {row.change_pct}%
                      </span>
                    </td>
                    <td className="py-3 pl-4 text-right">
                      {canApply ? (
                        <PrimaryButton disabled={busy !== null} onClick={() => void apply(row)}>
                          {busy === key ? "Applying…" : "Apply"}
                        </PrimaryButton>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </article>
  );
}

function Slices({ title, rows, money }: { title: string; rows: ShrinkSlice[]; money: (cents: number) => string }) {
  return (
    <article className="rounded-card border border-line bg-white p-5">
      <h3 className="text-base font-semibold">{title}</h3>
      {rows.length === 0 ? <p className="mt-3 text-sm text-charcoal/60">Nothing lost.</p> : null}
      <ul className="mt-3 space-y-2">
        {rows.map((row) => (
          <li key={row.label}>
            <div className="flex justify-between text-sm">
              <span>{row.label}</span>
              <span className="tabular-nums">{money(row.lost_cents)}</span>
            </div>
            <div className="mt-1 h-1.5 rounded-full bg-surface">
              <div className="h-1.5 rounded-full bg-accent" style={{ width: `${Math.max(2, row.share_bps / 100)}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </article>
  );
}

function ShrinkTab() {
  const [days, setDays] = useState(90);
  const { data, error } = useReport<ShrinkReport>(`/api/v1/insights/shrink?days=${days}`, "Could not load shrink.");
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  const money = (cents: number) => formatMoney(cents, data.currency);
  const peak = Math.max(1, ...data.weeks.map((week) => week.lost_cents));
  return (
    <>
      <article className="rounded-card border border-line bg-white p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h3 className="text-base font-semibold">Stock lost, at cost</h3>
          <DaysPicker value={days} options={[30, 90, 365]} onChange={setDays} />
        </div>
        <dl className="mt-4 grid gap-3 sm:grid-cols-4">
          <div className="rounded-2xl bg-charcoal p-4 text-white">
            <dt className="text-xs text-white/60">Net shrink</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{money(data.net_cents)}</dd>
          </div>
          <div className="rounded-2xl bg-surface p-4">
            <dt className="text-xs text-charcoal/60">Share of net sales</dt>
            <dd className={`mt-1 text-2xl font-semibold tabular-nums ${data.shrink_bps > 150 ? "text-red-600" : ""}`}>
              {pct(data.shrink_bps)}
            </dd>
          </div>
          <div className="rounded-2xl bg-surface p-4">
            <dt className="text-xs text-charcoal/60">Written off or missing</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{money(data.lost_cents)}</dd>
          </div>
          <div className="rounded-2xl bg-surface p-4">
            <dt className="text-xs text-charcoal/60">Found on counts</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{money(data.found_cents)}</dd>
          </div>
        </dl>
        {data.weeks.length > 0 ? (
          <div className="mt-5">
            <p className="text-xs text-charcoal/60">Lost per week</p>
            <div className="mt-2 flex h-24 items-end gap-1" role="img" aria-label="Shrink per week">
              {data.weeks.map((week) => (
                <div
                  key={week.week_start}
                  title={`Week of ${week.week_start}: ${money(week.lost_cents)}`}
                  className="flex-1 rounded-t bg-accent/80"
                  style={{ height: `${Math.max(3, (week.lost_cents / peak) * 100)}%` }}
                />
              ))}
            </div>
          </div>
        ) : null}
        {data.hotspots.length > 0 ? (
          <ul className="mt-5 space-y-2">
            {data.hotspots.map((hotspot) => (
              <li key={hotspot.category} className="rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
                {hotspot.summary}
              </li>
            ))}
          </ul>
        ) : null}
      </article>
      <div className="grid gap-4 lg:grid-cols-3">
        <Slices title="By reason" rows={data.by_reason} money={money} />
        <Slices title="By category" rows={data.by_category} money={money} />
        <Slices title="By branch" rows={data.by_store} money={money} />
      </div>
      <article className="overflow-x-auto rounded-card border border-line bg-white p-5">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold">Most lost</h3>
          <Link to="/inventory/counts" className="text-xs font-semibold text-accent hover:underline">
            Schedule a stock count
          </Link>
        </div>
        {data.top_products.length === 0 ? (
          <p className="mt-3 text-sm text-charcoal/60">
            No write-offs, theft or count differences recorded in the last {days} days.
          </p>
        ) : null}
        <table className={`mt-3 w-full min-w-[720px] text-left text-sm ${data.top_products.length ? "" : "hidden"}`}>
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Product</th>
              <th className="pb-2 text-right font-medium">Lost</th>
              <th className="pb-2 text-right font-medium">At cost</th>
              <th className="pb-2 text-right font-medium">Events</th>
              <th className="pb-2 text-right font-medium">Of what left the shelf</th>
            </tr>
          </thead>
          <tbody>
            {data.top_products.map((row) => (
              <tr key={row.product_id} className="border-t border-line">
                <td className="py-2">
                  <span className="block font-medium">{row.name}</span>
                  <span className="block text-[11px] text-charcoal/50">{row.category}</span>
                </td>
                <td className="py-2 text-right tabular-nums">
                  {row.sold_by_weight ? formatWeight(row.lost_units) : row.lost_units}
                </td>
                <td className="py-2 text-right tabular-nums">{money(row.lost_cents)}</td>
                <td className="py-2 text-right tabular-nums">{row.events}</td>
                <td className="py-2 text-right tabular-nums">{pct(row.shrink_rate_bps)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </>
  );
}
