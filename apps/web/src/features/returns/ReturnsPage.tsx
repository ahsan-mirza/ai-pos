import {
  AnalyticsTimeframe,
  formatMoney,
  type OverrideReason,
  type RefundMethod,
  type ReturnsAnalytics,
} from "@ai-pos/shared-types";
import { AlertTriangle } from "lucide-react";
import { useEffect, useState } from "react";
import { Sparkline, SplitBar } from "../../components/charts/Charts";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiGet } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { sampleReturns } from "./sample";

const options = [
  { value: AnalyticsTimeframe.AllTime, label: "All time" },
  { value: AnalyticsTimeframe.Weekly, label: "Weekly" },
  { value: AnalyticsTimeframe.Monthly, label: "Monthly" },
] as const;

const tenderLabels: Record<RefundMethod, string> = {
  original_card: "Card",
  original_bnpl: "Pay later",
  cash: "Cash",
  store_credit: "Credit",
};
const tenderColors: Record<RefundMethod, string> = {
  original_card: "#FFFFFF",
  original_bnpl: "rgba(255,255,255,0.7)",
  cash: "#222026",
  store_credit: "rgba(255,255,255,0.45)",
};

const conditionLabels: Record<string, string> = {
  unopened_resealable: "Unopened",
  open_box: "Open box",
  defective_doa: "Defective / DOA",
  tags_attached: "Tags attached",
  worn: "Worn",
  damaged: "Damaged",
};

const reasonLabels: Record<OverrideReason, string> = {
  no_refund_permission: "No refund permission",
  outside_window: "Outside window",
  fee_waived: "Fee waived",
  final_sale: "Final sale",
};

const percent = (bps: number) => `${(bps / 100).toFixed(1)}%`;
const dateTime = (value: string) =>
  new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export function ReturnsPage() {
  const { currency } = useCurrency();
  const [timeframe, setTimeframe] = useState<AnalyticsTimeframe>(AnalyticsTimeframe.AllTime);
  const [data, setData] = useState<ReturnsAnalytics>(sampleReturns[AnalyticsTimeframe.AllTime]);
  const [source, setSource] = useState<"sample" | "live">("sample");

  useEffect(() => {
    const controller = new AbortController();
    setData({ ...sampleReturns[timeframe], currency });
    setSource("sample");
    apiGet<ReturnsAnalytics>(`/api/v1/returns/analytics?timeframe=${timeframe}&currency=${currency}`)
      .then((live) => {
        if (!controller.signal.aborted) {
          setData(live);
          setSource("live");
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setSource("sample");
      });
    return () => controller.abort();
  }, [timeframe, currency]);

  const conditionMax = Math.max(...data.conditions.map((item) => item.units), 1);
  const flagged = data.cashiers.filter((row) => row.flagged).length;

  return (
    <section className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h2 className="font-sans text-[28px] font-semibold leading-tight tracking-tight md:text-[32px]">
            Returns &amp; Refunds
          </h2>
          <p className="mt-1 text-sm text-charcoal/60">
            {source === "sample"
              ? "Showing sample figures. Live returns appear when the API is reachable."
              : `Refunds processed in ${data.currency}.`}
          </p>
        </div>
        <SegmentedControl label="Timeframe" value={timeframe} options={options} onChange={setTimeframe} />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3 lg:gap-6">
        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl bg-charcoal p-6 text-white">
          <div>
            <p className="text-sm font-medium text-white/60">Refunded</p>
            <p className="mt-3 break-words font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums xl:text-[40px]">
              {formatMoney(data.refund_cents, data.currency)}
            </p>
            <p className="mt-2 text-sm text-white/60">
              <span className="font-semibold tabular-nums text-white">{data.return_count.toLocaleString()}</span> returns
              · <span className="font-semibold tabular-nums text-white">{data.units_returned.toLocaleString()}</span>{" "}
              units
            </p>
          </div>
          <Sparkline values={data.refund_series} stroke="#FFFFFF" />
        </article>

        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl bg-accent p-6 text-white">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-white/80">Return rate</p>
              <p className="mt-3 font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums xl:text-[40px]">
                {percent(data.return_rate_bps)}
              </p>
              <p className="mt-2 text-sm text-white/80 tabular-nums">
                of {data.units_sold.toLocaleString()} units sold
              </p>
            </div>
            <span className="shrink-0 rounded-full bg-white/20 px-3 py-1.5 text-xs font-semibold tabular-nums text-white">
              {percent(data.defective_rate_bps)} defective
            </span>
          </div>
          <SplitBar
            segments={data.tenders.map((item) => ({
              label: tenderLabels[item.method],
              amount: item.amount_cents,
              color: tenderColors[item.method],
            }))}
          />
        </article>

        <article className="flex min-h-[236px] flex-col justify-between gap-6 rounded-2xl border border-line bg-white p-6">
          <div className="flex items-start justify-between gap-3">
            <div>
              <p className="text-sm font-medium text-charcoal/60">Manager overrides</p>
              <p className="mt-3 font-sans text-[36px] font-semibold leading-none tracking-tight tabular-nums text-charcoal xl:text-[40px]">
                {data.override_count.toLocaleString()}
              </p>
              <p className="mt-2 text-sm text-charcoal/60 tabular-nums">
                {formatMoney(data.restocking_fee_cents, data.currency)} restocking fees kept
              </p>
            </div>
            {flagged > 0 ? (
              <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent/10 px-3 py-1.5 text-xs font-semibold text-accent">
                <AlertTriangle size={12} aria-hidden="true" />
                {flagged} flagged
              </span>
            ) : null}
          </div>
          <ul className="space-y-2.5">
            {data.conditions.map((item) => (
              <li key={item.condition} className="grid grid-cols-[96px_1fr_32px] items-center gap-3 text-xs">
                <span className="font-medium text-charcoal/70">{conditionLabels[item.condition] ?? item.condition.replace(/_/g, " ")}</span>
                <span className="h-2.5 rounded-full bg-surface">
                  <span
                    className={`block h-full rounded-full ${
                      item.condition === "defective_doa" ? "bg-accent" : "bg-charcoal"
                    }`}
                    style={{ width: `${(item.units / conditionMax) * 100}%` }}
                  />
                </span>
                <span className="text-right font-semibold tabular-nums">{item.units}</span>
              </li>
            ))}
          </ul>
        </article>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)] xl:gap-6">
        <article className="rounded-2xl border border-line bg-white p-6">
          <div className="mb-5 flex items-end justify-between gap-3">
            <div>
              <h3 className="font-sans text-lg font-semibold">Most returned products</h3>
              <p className="text-sm text-charcoal/60">Ranked by defective units, then units returned.</p>
            </div>
          </div>
          {data.top_products.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-line p-6 text-sm text-charcoal/60">
              No returns in this period.
            </p>
          ) : (
            <div className="-mx-6 overflow-x-auto px-6">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-xs uppercase tracking-[0.12em] text-charcoal/50">
                  <tr>
                    <th className="pb-3 font-medium">Product</th>
                    <th className="pb-3 text-right font-medium">Returned</th>
                    <th className="pb-3 text-right font-medium">Defective</th>
                    <th className="pb-3 text-right font-medium">Rate</th>
                    <th className="pb-3 text-right font-medium">Refunded</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line tabular-nums">
                  {data.top_products.map((row) => (
                    <tr key={row.product_id}>
                      <td className="py-3 pr-3">
                        <p className="font-semibold">{row.name}</p>
                        <p className="text-xs text-charcoal/50">
                          {row.sku} · {row.category}
                        </p>
                      </td>
                      <td className="py-3 text-right">
                        {row.units_returned}
                        <span className="text-charcoal/40"> / {row.units_sold}</span>
                      </td>
                      <td className="py-3 text-right">
                        <span
                          className={`inline-flex min-w-8 justify-center rounded-full px-2 py-0.5 text-xs font-semibold ${
                            row.defective_units > 0 ? "bg-accent text-white" : "bg-surface text-charcoal/60"
                          }`}
                        >
                          {row.defective_units}
                        </span>
                      </td>
                      <td className="py-3 text-right font-semibold">{percent(row.return_rate_bps)}</td>
                      <td className="py-3 text-right">{formatMoney(row.refund_cents, data.currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>

        <article className="rounded-2xl border border-line bg-white p-6">
          <div className="mb-5">
            <h3 className="font-sans text-lg font-semibold">Cashier return frequency</h3>
            <p className="text-sm text-charcoal/60">Flagged at 3 or more manager overrides.</p>
          </div>
          {data.cashiers.length === 0 ? (
            <p className="rounded-2xl border border-dashed border-line p-6 text-sm text-charcoal/60">
              No returns in this period.
            </p>
          ) : (
            <ul className="space-y-3">
              {data.cashiers.map((row) => (
                <li
                  key={row.cashier_id}
                  className={`rounded-2xl p-4 ${row.flagged ? "bg-charcoal text-white" : "bg-surface text-charcoal"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="flex items-center gap-2 font-semibold">
                        <span className="truncate">{row.full_name}</span>
                        {row.flagged ? (
                          <span className="rounded-full bg-accent px-2 py-0.5 text-[10px] font-semibold uppercase">
                            Review
                          </span>
                        ) : null}
                      </p>
                      <p className={`text-xs ${row.flagged ? "text-white/60" : "text-charcoal/50"}`}>
                        {row.role_name || "Staff"} · last {dateTime(row.last_return_at)}
                      </p>
                    </div>
                    <p className="text-right font-semibold tabular-nums">{formatMoney(row.refund_cents, data.currency)}</p>
                  </div>
                  <dl className="mt-3 grid grid-cols-3 gap-2 text-xs tabular-nums">
                    {[
                      ["Returns", row.return_count],
                      ["Overrides", row.override_count],
                      ["Late", row.outside_window_count],
                    ].map(([label, value]) => (
                      <div key={label} className={`rounded-xl px-3 py-2 ${row.flagged ? "bg-white/10" : "bg-white"}`}>
                        <dt className={row.flagged ? "text-white/60" : "text-charcoal/50"}>{label}</dt>
                        <dd className="text-base font-semibold">{value}</dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>

      <article className="rounded-2xl border border-line bg-white p-6">
        <div className="mb-5">
          <h3 className="font-sans text-lg font-semibold">Override audit log</h3>
          <p className="text-sm text-charcoal/60">Every return a manager approved, with the reason they gave.</p>
        </div>
        {data.overrides.length === 0 ? (
          <p className="rounded-2xl border border-dashed border-line p-6 text-sm text-charcoal/60">
            No overrides in this period.
          </p>
        ) : (
          <div className="-mx-6 overflow-x-auto px-6">
            <table className="w-full min-w-[720px] text-left text-sm">
              <thead className="text-xs uppercase tracking-[0.12em] text-charcoal/50">
                <tr>
                  <th className="pb-3 font-medium">When</th>
                  <th className="pb-3 font-medium">Cashier</th>
                  <th className="pb-3 font-medium">Approved by</th>
                  <th className="pb-3 font-medium">Override</th>
                  <th className="pb-3 font-medium">Note</th>
                  <th className="pb-3 text-right font-medium">Refund</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.overrides.map((row) => (
                  <tr key={row.id} className="align-top">
                    <td className="py-3 pr-3 tabular-nums text-charcoal/70">{dateTime(row.created_at)}</td>
                    <td className="py-3 pr-3 font-semibold">{row.cashier_name}</td>
                    <td className="py-3 pr-3">{row.approver_name ?? "—"}</td>
                    <td className="py-3 pr-3">
                      <span className="flex flex-wrap gap-1">
                        {row.reasons.map((reason) => (
                          <span
                            key={reason}
                            className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                              reason === "outside_window" ? "bg-accent text-white" : "bg-surface text-charcoal"
                            }`}
                          >
                            {reasonLabels[reason]}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="max-w-xs py-3 pr-3 text-charcoal/70">{row.note || "—"}</td>
                    <td className="py-3 text-right font-semibold tabular-nums">
                      {formatMoney(row.refund_cents, data.currency)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </article>
    </section>
  );
}
