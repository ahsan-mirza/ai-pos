import {
  EXPENSE_CATEGORY_LABELS,
  formatMoney,
  type AgedStockReport,
  type DiscountReport,
  type ExpenseCategory,
  type PnlReport,
  type PnlRow,
  type StaffSalesReport,
  type ValuationReport,
} from "@ai-pos/shared-types";
import { Download } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, FilterSelect, GhostButton, TextField } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiBlob, apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

type Tab = "pnl" | "valuation" | "aged-stock" | "staff" | "discounts";

const iso = (value: Date) => value.toISOString().slice(0, 10);
const yearStart = () => `${new Date().getFullYear()}-01-01`;
const percent = (bps: number) => `${(bps / 100).toFixed(1)}%`;
const monthLabel = (value: string) =>
  value === "ALL" ? "Total" : new Date(`${value}-01T00:00:00`).toLocaleDateString(undefined, { month: "short", year: "numeric" });

function Kpi({ label, value, hint, tone }: { label: string; value: string; hint: string; tone: "dark" | "accent" | "light" }) {
  const styles = {
    dark: "rounded-card bg-charcoal p-6 text-white",
    accent: "rounded-card bg-accent p-6 text-white",
    light: "rounded-card border border-line bg-white p-6",
  }[tone];
  const muted = tone === "light" ? "text-charcoal/60" : tone === "accent" ? "text-white/80" : "text-white/60";
  return (
    <article className={styles}>
      <p className={`text-sm ${muted}`}>{label}</p>
      <p className="mt-4 text-3xl font-semibold tabular-nums">{value}</p>
      <p className={`mt-2 text-xs ${muted}`}>{hint}</p>
    </article>
  );
}

export function ManagementReportsPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const [tab, setTab] = useState<Tab>("pnl");
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [from, setFrom] = useState(yearStart());
  const [to, setTo] = useState(iso(new Date()));
  const [pnl, setPnl] = useState<PnlReport | null>(null);
  const [valuation, setValuation] = useState<ValuationReport | null>(null);
  const [aged, setAged] = useState<AgedStockReport | null>(null);
  const [carryingRate, setCarryingRate] = useState(25);
  const [staff, setStaff] = useState<StaffSalesReport | null>(null);
  const [discounts, setDiscounts] = useState<DiscountReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);
  const scope = storeId ? `&store_id=${storeId}` : "";

  const load = useCallback(async () => {
    try {
      if (tab === "pnl") setPnl(await apiGet<PnlReport>(`/api/v1/reports/management/pnl?from=${from}&to=${to}${scope}`));
      if (tab === "valuation") setValuation(await apiGet<ValuationReport>(`/api/v1/reports/management/valuation?x=1${scope}`));
      if (tab === "aged-stock") {
        setAged(await apiGet<AgedStockReport>(`/api/v1/reports/management/aged-stock?carrying_rate_pct=${carryingRate}${scope}`));
      }
      if (tab === "staff") setStaff(await apiGet<StaffSalesReport>(`/api/v1/reports/management/staff?from=${from}&to=${to}${scope}`));
      if (tab === "discounts") {
        setDiscounts(await apiGet<DiscountReport>(`/api/v1/reports/management/discounts?from=${from}&to=${to}${scope}`));
      }
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build the report."));
    }
  }, [tab, from, to, scope, carryingRate]);

  useEffect(() => {
    void load();
  }, [load]);

  const download = async () => {
    try {
      const blob = await apiBlob(
        `/api/v1/reports/management/${tab}.csv?from=${from}&to=${to}&carrying_rate_pct=${carryingRate}${scope}`,
      );
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${tab}-${from}-${to}.csv`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(errorMessage(caught, "Could not export the report."));
    }
  };

  const dated = tab === "pnl" || tab === "staff" || tab === "discounts";

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Management reports</h2>
            <p className="text-sm text-charcoal/60">Profit by branch, what the stock is worth, what is not selling, and who sells what.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-52"
              />
            )}
            {dated ? (
              <>
                <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
                <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
              </>
            ) : null}
            <GhostButton onClick={() => void download()}>
              <Download size={15} aria-hidden="true" className="-ml-1 mr-1.5" /> CSV
            </GhostButton>
          </div>
        </div>
        <div className="mt-5">
          <SegmentedControl
            label="Report"
            value={tab}
            options={[
              { value: "pnl", label: "Profit & loss" },
              { value: "valuation", label: "Stock value" },
              { value: "aged-stock", label: "Slow & dead stock" },
              { value: "staff", label: "Sales by staff" },
              { value: "discounts", label: "Discounts" },
            ]}
            onChange={setTab}
          />
        </div>
      </div>
      <ErrorNote message={error} />

      {tab === "pnl" && pnl ? <PnlView report={pnl} money={money} /> : null}

      {tab === "valuation" && valuation ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Kpi tone="dark" label="Stock at cost" value={money(valuation.cost_value_cents)} hint={`${valuation.units.toLocaleString()} units on hand`} />
            <Kpi
              tone="accent"
              label="At shelf price"
              value={money(valuation.retail_value_cents)}
              hint={`${money(valuation.retail_value_cents - valuation.cost_value_cents)} potential margin`}
            />
            <Kpi
              tone="light"
              label="Estimated cost"
              value={valuation.estimated_units.toLocaleString()}
              hint="Units with no purchase batch, valued at the latest purchase cost"
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
            <article className="rounded-card border border-line bg-white p-6">
              <h3 className="font-semibold">By category</h3>
              <ul className="mt-4 space-y-3">
                {valuation.by_category.map((group) => (
                  <li key={group.key}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span>{group.key}</span>
                      <span className="font-semibold tabular-nums">{money(group.cost_value_cents)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-surface">
                      <div
                        className="h-1.5 rounded-full bg-accent"
                        style={{ width: `${(group.cost_value_cents / Math.max(1, valuation.by_category[0]?.cost_value_cents ?? 1)) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </article>
            <article className="rounded-card border border-line bg-white p-6">
              <h3 className="mb-3 font-semibold">Most valuable stock</h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                    <tr>
                      <th className="pb-2 font-medium">Product</th>
                      <th className="pb-2 font-medium">Branch</th>
                      <th className="pb-2 text-right font-medium">On hand</th>
                      <th className="pb-2 text-right font-medium">Unit cost</th>
                      <th className="pb-2 text-right font-medium">At cost</th>
                    </tr>
                  </thead>
                  <tbody>
                    {valuation.rows.slice(0, 50).map((row) => (
                      <tr key={`${row.product_id}-${row.store_id}`} className="border-t border-line">
                        <td className="py-2">
                          <span className="block font-medium">{row.name}</span>
                          <span className="block font-mono text-xs text-charcoal/50">{row.sku}</span>
                        </td>
                        <td className="py-2">{row.store_code}</td>
                        <td className="py-2 text-right tabular-nums">{row.on_hand}</td>
                        <td className="py-2 text-right tabular-nums">
                          {money(row.unit_cost_cents)}
                          {row.estimated ? <span className="block text-[11px] text-charcoal/40">partly estimated</span> : null}
                        </td>
                        <td className="py-2 text-right font-semibold tabular-nums">{money(row.cost_value_cents)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </div>
        </>
      ) : null}

      {tab === "aged-stock" && aged ? (
        <>
          <div className="grid gap-4 md:grid-cols-4">
            <Kpi tone="dark" label="Dead stock" value={money(aged.dead_value_cents)} hint={`Not sold for ${aged.dead_days}+ days, at cost`} />
            <Kpi tone="accent" label="Slow stock" value={money(aged.slow_value_cents)} hint={`No sale in ${aged.slow_days} days, or over 6 months of cover`} />
            <Kpi
              tone="light"
              label="Holding cost / month"
              value={money(aged.holding_cost_month_cents ?? 0)}
              hint={`${(aged.carrying_rate_bps ?? 2500) / 100}% a year of cost; ${money(aged.holding_cost_to_date_cents ?? 0)} since last sale`}
            />
            <Kpi tone="light" label="Lines to act on" value={String(aged.rows.length)} hint="Sorted by value, dead first" />
          </div>
          <div className="flex flex-wrap items-center gap-3 text-sm text-charcoal/70">
            <label className="flex items-center gap-2">
              Annual carrying rate
              <select
                value={carryingRate}
                onChange={(event) => setCarryingRate(Number(event.target.value))}
                className="h-9 rounded-lg border border-line bg-white px-2 text-sm"
              >
                {[10, 15, 20, 25, 30, 40].map((rate) => (
                  <option key={rate} value={rate}>
                    {rate}%
                  </option>
                ))}
              </select>
            </label>
            <span className="text-xs text-charcoal/50">
              Capital, space, insurance and shrink as a share of stock cost. Markdowns never go below the margin floor, or cost.
            </span>
          </div>
          <article className="rounded-card border border-line bg-white p-6">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[1080px] text-left text-sm">
                <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                  <tr>
                    <th className="pb-2 font-medium">Product</th>
                    <th className="pb-2 font-medium">Branch</th>
                    <th className="pb-2 text-right font-medium">On hand</th>
                    <th className="pb-2 text-right font-medium">At cost</th>
                    <th className="pb-2 text-right font-medium">Last sale</th>
                    <th className="pb-2 text-right font-medium">Cover</th>
                    <th className="pb-2 text-right font-medium">Holding / mo</th>
                    <th className="pb-2 text-right font-medium">Clearance price</th>
                    <th className="pb-2 pl-6 font-medium">Do this</th>
                  </tr>
                </thead>
                <tbody>
                  {aged.rows.map((row) => (
                    <tr key={`${row.product_id}-${row.store_id}`} className="border-t border-line align-top">
                      <td className="py-2.5">
                        <span className="block font-medium">{row.name}</span>
                        <span className="block text-xs text-charcoal/50">
                          <span
                            className={`mr-1.5 rounded-full px-2 py-0.5 text-[10px] font-semibold ${
                              row.status === "DEAD" ? "bg-charcoal text-white" : "bg-accent/10 text-accent"
                            }`}
                          >
                            {row.status === "DEAD" ? "Dead" : "Slow"}
                          </span>
                          {row.sku}
                        </span>
                      </td>
                      <td className="py-2.5">{row.store_code}</td>
                      <td className="py-2.5 text-right tabular-nums">{row.on_hand}</td>
                      <td className="py-2.5 text-right font-semibold tabular-nums">{money(row.cost_value_cents)}</td>
                      <td className="py-2.5 text-right tabular-nums">
                        {row.days_since_sale === null ? "Never" : `${row.days_since_sale}d ago`}
                        <span className="block text-[11px] text-charcoal/50">{row.units_sold_90d} sold in 90d</span>
                      </td>
                      <td className="py-2.5 text-right tabular-nums">{row.cover_days === null ? "—" : `${row.cover_days.toLocaleString()}d`}</td>
                      <td className="py-2.5 text-right tabular-nums">{money(row.holding_cost_month_cents ?? 0)}</td>
                      <td className="py-2.5 text-right tabular-nums">
                        {row.suggested_price_cents ? (
                          <>
                            <span className="font-semibold">{money(row.suggested_price_cents)}</span>
                            <span className="block text-[11px] text-charcoal/50">
                              −{row.markdown_pct}% from {money(row.price_cents ?? 0)}
                            </span>
                          </>
                        ) : (
                          <span className="text-xs text-charcoal/50">At floor</span>
                        )}
                      </td>
                      <td className="py-2.5 pl-6 text-xs text-charcoal/70">{row.suggestion}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {aged.rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Everything on the shelves is selling.</p> : null}
            </div>
          </article>
        </>
      ) : null}

      {tab === "staff" && staff ? (
        <article className="rounded-card border border-line bg-white p-6">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[900px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                <tr>
                  <th className="pb-2 font-medium">Staff</th>
                  <th className="pb-2 text-right font-medium">Sales</th>
                  <th className="pb-2 text-right font-medium">Revenue</th>
                  <th className="pb-2 text-right font-medium">Gross profit</th>
                  <th className="pb-2 text-right font-medium">Margin</th>
                  <th className="pb-2 text-right font-medium">Avg basket</th>
                  <th className="pb-2 text-right font-medium">Discounts given</th>
                  <th className="pb-2 text-right font-medium">Returns</th>
                </tr>
              </thead>
              <tbody>
                {staff.rows.map((row) => (
                  <tr key={row.user_id} className="border-t border-line">
                    <td className="py-2.5 font-medium">{row.name}</td>
                    <td className="py-2.5 text-right tabular-nums">
                      {row.sales}
                      <span className="block text-[11px] text-charcoal/50">{row.units} units</span>
                    </td>
                    <td className="py-2.5 text-right font-semibold tabular-nums">{money(row.revenue_cents)}</td>
                    <td className="py-2.5 text-right tabular-nums">{money(row.gross_profit_cents)}</td>
                    <td className="py-2.5 text-right tabular-nums">{percent(row.gross_margin_bps)}</td>
                    <td className="py-2.5 text-right tabular-nums">{money(row.average_basket_cents)}</td>
                    <td className="py-2.5 text-right tabular-nums">
                      {money(row.promotion_discount_cents + row.override_discount_cents)}
                      {row.override_discount_cents ? (
                        <span className="block text-[11px] text-accent">{money(row.override_discount_cents)} by price override</span>
                      ) : null}
                    </td>
                    <td className="py-2.5 text-right tabular-nums">
                      {row.returns}
                      {row.returns ? <span className="block text-[11px] text-charcoal/50">{money(row.returns_cents)}</span> : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {staff.rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No sales in this period.</p> : null}
          </div>
        </article>
      ) : null}

      {tab === "discounts" && discounts ? (
        <>
          <div className="grid gap-4 md:grid-cols-3">
            <Kpi tone="dark" label="Cashier discounts" value={money(discounts.total_cents)} hint="Given at the till, before VAT" />
            <Kpi
              tone="accent"
              label="Discounted lines"
              value={discounts.rows.reduce((sum, row) => sum + row.lines, 0).toLocaleString()}
              hint={`${discounts.rows.reduce((sum, row) => sum + row.approved_lines, 0)} needed a manager`}
            />
            <Kpi
              tone="light"
              label="Top reason"
              value={discounts.by_reason[0]?.reason_label ?? "—"}
              hint={discounts.by_reason[0] ? money(discounts.by_reason[0].discount_cents) : "No discounts in this period"}
            />
          </div>
          <div className="grid gap-4 xl:grid-cols-[22rem_minmax(0,1fr)]">
            <article className="rounded-card border border-line bg-white p-6">
              <h3 className="font-semibold">By reason</h3>
              <ul className="mt-4 space-y-3">
                {discounts.by_reason.map((group) => (
                  <li key={group.reason}>
                    <div className="flex items-baseline justify-between text-sm">
                      <span>
                        {group.reason_label} <span className="text-xs text-charcoal/50">· {group.lines} lines</span>
                      </span>
                      <span className="font-semibold tabular-nums">{money(group.discount_cents)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-surface">
                      <div
                        className="h-1.5 rounded-full bg-accent"
                        style={{ width: `${(group.discount_cents / Math.max(1, discounts.by_reason[0]?.discount_cents ?? 1)) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            </article>
            <article className="rounded-card border border-line bg-white p-6">
              <h3 className="mb-3 font-semibold">By cashier</h3>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[560px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                    <tr>
                      <th className="pb-2 font-medium">Staff</th>
                      <th className="pb-2 font-medium">Reason</th>
                      <th className="pb-2 text-right font-medium">Lines</th>
                      <th className="pb-2 text-right font-medium">Discount</th>
                      <th className="pb-2 text-right font-medium">Avg off</th>
                      <th className="pb-2 text-right font-medium">Approved</th>
                    </tr>
                  </thead>
                  <tbody>
                    {discounts.rows.map((row) => (
                      <tr key={`${row.user_id}-${row.reason}`} className="border-t border-line">
                        <td className="py-2 font-medium">{row.name}</td>
                        <td className="py-2">{row.reason_label}</td>
                        <td className="py-2 text-right tabular-nums">{row.lines}</td>
                        <td className="py-2 text-right font-semibold tabular-nums">{money(row.discount_cents)}</td>
                        <td className="py-2 text-right tabular-nums">{percent(row.share_bps)}</td>
                        <td className={`py-2 text-right tabular-nums ${row.approved_lines ? "text-accent" : ""}`}>{row.approved_lines}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {discounts.rows.length === 0 ? (
                  <p className="py-8 text-sm text-charcoal/60">No cashier discounts in this period.</p>
                ) : null}
              </div>
            </article>
          </div>
        </>
      ) : null}
    </section>
  );
}

function PnlView({ report, money }: { report: PnlReport; money: (cents: number) => string }) {
  const total = report.total;
  const months = [...new Set(report.rows.map((row) => row.month))];
  const byMonth = months.map((month) => {
    const rows = report.rows.filter((row) => row.month === month);
    return rows.length === 1 ? rows[0]! : sumRows(month, rows);
  });
  const categories = [...new Set(report.rows.flatMap((row) => Object.keys(row.expenses)))].sort() as ExpenseCategory[];
  const columns = [...byMonth, total];

  const line = (label: string, pick: (row: PnlRow) => number, options: { strong?: boolean; negative?: boolean } = {}) => (
    <tr className={`border-t border-line ${options.strong ? "font-semibold" : ""}`}>
      <td className={`py-2 pr-4 ${options.strong ? "" : "text-charcoal/70"}`}>{label}</td>
      {columns.map((row) => {
        const value = pick(row);
        return (
          <td key={row.month} className={`py-2 text-right tabular-nums ${options.strong && value < 0 ? "text-accent" : ""}`}>
            {value === 0 && !options.strong ? "—" : options.negative ? `(${money(value)})` : money(value)}
          </td>
        );
      })}
    </tr>
  );

  return (
    <>
      <div className="grid gap-4 md:grid-cols-3">
        <Kpi tone="dark" label="Revenue" value={money(total.revenue_cents)} hint={`After ${money(total.returns_cents)} of returns, before VAT`} />
        <Kpi tone="accent" label="Gross profit" value={money(total.gross_profit_cents)} hint={`${percent(total.gross_margin_bps)} margin on FIFO cost`} />
        <Kpi
          tone="light"
          label="Operating profit"
          value={money(total.operating_profit_cents)}
          hint={report.cost_estimated ? "Some sale lines have no recorded cost" : "After expenses, other purchases and shrinkage"}
        />
      </div>
      <article className="rounded-card border border-line bg-white p-6">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium" />
                {columns.map((row) => (
                  <th key={row.month} className="pb-2 text-right font-medium">
                    {monthLabel(row.month)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {line("Sales", (row) => row.net_sales_cents)}
              {line("Returns", (row) => row.returns_cents, { negative: true })}
              {line("Revenue", (row) => row.revenue_cents, { strong: true })}
              {line("Cost of goods sold", (row) => row.cogs_cents, { negative: true })}
              {line("Gross profit", (row) => row.gross_profit_cents, { strong: true })}
              {categories.map((category) => (
                <tr key={category} className="border-t border-line">
                  <td className="py-2 pr-4 text-charcoal/70">{EXPENSE_CATEGORY_LABELS[category] ?? category}</td>
                  {columns.map((row) => (
                    <td key={row.month} className="py-2 text-right tabular-nums">
                      {row.expenses[category] ? `(${money(row.expenses[category])})` : "—"}
                    </td>
                  ))}
                </tr>
              ))}
              {line("Other purchases", (row) => row.other_purchases_cents, { negative: true })}
              {line("Stock written off", (row) => row.shrinkage_cents, { negative: true })}
              {line("Operating profit", (row) => row.operating_profit_cents, { strong: true })}
            </tbody>
          </table>
          {report.rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No activity in this period.</p> : null}
        </div>
      </article>
      {report.by_store.length > 1 ? (
        <article className="rounded-card border border-line bg-white p-6">
          <h3 className="mb-3 font-semibold">By branch</h3>
          <table className="w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Branch</th>
                <th className="pb-2 text-right font-medium">Revenue</th>
                <th className="pb-2 text-right font-medium">Gross profit</th>
                <th className="pb-2 text-right font-medium">Margin</th>
                <th className="pb-2 text-right font-medium">Operating profit</th>
              </tr>
            </thead>
            <tbody>
              {report.by_store.map((row) => (
                <tr key={row.store_code} className="border-t border-line">
                  <td className="py-2 font-medium">{row.store_code}</td>
                  <td className="py-2 text-right tabular-nums">{money(row.revenue_cents)}</td>
                  <td className="py-2 text-right tabular-nums">{money(row.gross_profit_cents)}</td>
                  <td className="py-2 text-right tabular-nums">{percent(row.gross_margin_bps)}</td>
                  <td className={`py-2 text-right font-semibold tabular-nums ${row.operating_profit_cents < 0 ? "text-accent" : ""}`}>
                    {money(row.operating_profit_cents)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      ) : null}
    </>
  );
}

function sumRows(month: string, rows: PnlRow[]): PnlRow {
  const expenses: Record<string, number> = {};
  for (const row of rows) for (const [key, value] of Object.entries(row.expenses)) expenses[key] = (expenses[key] ?? 0) + value;
  const sum = (pick: (row: PnlRow) => number) => rows.reduce((total, row) => total + pick(row), 0);
  const revenue = sum((row) => row.revenue_cents);
  const gross = sum((row) => row.gross_profit_cents);
  return {
    month,
    store_id: null,
    store_code: "ALL",
    net_sales_cents: sum((row) => row.net_sales_cents),
    returns_cents: sum((row) => row.returns_cents),
    revenue_cents: revenue,
    cogs_cents: sum((row) => row.cogs_cents),
    gross_profit_cents: gross,
    gross_margin_bps: revenue ? Math.round((gross * 10000) / revenue) : 0,
    expenses,
    other_purchases_cents: sum((row) => row.other_purchases_cents),
    shrinkage_cents: sum((row) => row.shrinkage_cents),
    operating_expenses_cents: sum((row) => row.operating_expenses_cents),
    operating_profit_cents: sum((row) => row.operating_profit_cents),
  };
}
