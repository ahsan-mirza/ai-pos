import { formatMoney, type TipReport } from "@ai-pos/shared-types";
import { HandCoins } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function startOfWeek(today: Date): Date {
  const day = (today.getDay() + 6) % 7;
  return new Date(today.getFullYear(), today.getMonth(), today.getDate() - day);
}

/** The tip pool: tips each member of staff earned (owed to them, not revenue) and the service charge taken. */
export function TipsReportPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const [range, setRange] = useState(() => ({ from: iso(startOfWeek(new Date())), to: iso(new Date()) }));
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [report, setReport] = useState<TipReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ from: range.from, to: range.to });
    if (storeId) params.set("store_id", storeId);
    return params.toString();
  }, [range, storeId]);

  const load = useCallback(async () => {
    try {
      setReport(await apiGet<TipReport>(`/api/v1/reports/tips?${query}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build the tip report."));
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const money = (cents: number) => formatMoney(cents, currency);
  const pool = report?.tips_cents ?? 0;

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Tips to pay out</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? money(pool) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">Owed to staff; not revenue and not taxed.</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Service charge</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? money(report.service_charge_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Revenue of the business.</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Bills with a tip or service charge</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? report.sales_count : "—"}</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-charcoal text-white">
              <HandCoins size={18} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Tips by server</h2>
              <p className="text-sm text-charcoal/60">A tip counts for the server chosen at payment, else the cashier.</p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="From" type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} />
            <TextField label="To" type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} />
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-56"
              />
            )}
          </div>
        </div>
        <ErrorNote message={error} />
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-charcoal/50">
              <th className="py-2">Server</th>
              <th className="py-2 text-right">Bills</th>
              <th className="py-2 text-right">Tips</th>
              <th className="py-2 text-right">Share of pool</th>
            </tr>
          </thead>
          <tbody>
            {(report?.by_server ?? []).map((row) => (
              <tr key={row.user_id ?? row.name} className="border-b border-line/60">
                <td className="py-2.5 font-medium">{row.name}</td>
                <td className="py-2.5 text-right tabular-nums">{row.sales_count}</td>
                <td className="py-2.5 text-right font-semibold tabular-nums">{money(row.tips_cents)}</td>
                <td className="py-2.5 text-right tabular-nums text-charcoal/60">
                  {pool > 0 ? `${((row.tips_cents / pool) * 100).toFixed(1)}%` : "—"}
                </td>
              </tr>
            ))}
            {report && report.by_server.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-6 text-center text-charcoal/50">
                  No tips in this period.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </section>
  );
}
