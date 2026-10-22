import { formatMoney, formatWeight, type UsageVarianceReport, type UsageVarianceRow } from "@ai-pos/shared-types";
import { Scale } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { storeOptions, useStores } from "../inventory/shared";
import { message } from "../customers/api";

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

function qty(row: UsageVarianceRow, value: number): string {
  return row.sold_by_weight ? formatWeight(value) : String(value);
}

/** Theoretical usage (what the recipes of the dishes sold call for) against actual usage after stock counts. */
export function RecipeUsagePage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const [range, setRange] = useState(() => {
    const today = new Date();
    return { from: iso(new Date(today.getFullYear(), today.getMonth(), 1)), to: iso(today) };
  });
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [report, setReport] = useState<UsageVarianceReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ from: range.from, to: range.to });
    if (storeId) params.set("store_id", storeId);
    return params.toString();
  }, [range, storeId]);

  const load = useCallback(async () => {
    try {
      setReport(await apiGet<UsageVarianceReport>(`/api/v1/recipes/variance?${query}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not build the usage report."));
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const lost = (report?.rows ?? []).reduce((sum, row) => sum + Math.max(0, row.variance_cost_cents), 0);

  return (
    <section className="rounded-card border border-line bg-white p-6">
      <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
            <Scale size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-xl font-semibold">Ingredient usage</h2>
            <p className="text-sm text-charcoal/60">
              Theoretical (recipes × dishes sold) against actual (drawn, corrected by stock counts and waste).
              {report && lost > 0 ? ` Over-use this period: ${formatMoney(lost, currency)}.` : ""}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <TextField label="From" type="date" value={range.from} onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))} />
          <TextField label="To" type="date" value={range.to} onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))} />
          {user?.store_id ? null : (
            <FilterSelect label="Branch" value={storeId} options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]} onChange={setStoreId} className="w-56" />
          )}
        </div>
      </div>
      <ErrorNote message={error} />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-charcoal/50">
              <th className="py-2">Ingredient</th>
              <th className="py-2 text-right">Theoretical</th>
              <th className="py-2 text-right">Drawn</th>
              <th className="py-2 text-right">Count / waste</th>
              <th className="py-2 text-right">Actual</th>
              <th className="py-2 text-right">Variance</th>
              <th className="py-2 text-right">Cost</th>
            </tr>
          </thead>
          <tbody>
            {(report?.rows ?? []).map((row) => {
              const share = row.theoretical > 0 ? (row.variance / row.theoretical) * 100 : 0;
              return (
                <tr key={row.ingredient_id} className="border-b border-line/60">
                  <td className="py-2.5">
                    <span className="font-medium">{row.name}</span>
                    <span className="ml-2 font-mono text-xs text-charcoal/50">{row.sku}</span>
                  </td>
                  <td className="py-2.5 text-right tabular-nums">{qty(row, row.theoretical)}</td>
                  <td className="py-2.5 text-right tabular-nums">{qty(row, row.drawn)}</td>
                  <td className="py-2.5 text-right tabular-nums">{row.adjustments ? qty(row, row.adjustments) : "—"}</td>
                  <td className="py-2.5 text-right tabular-nums">{qty(row, row.actual)}</td>
                  <td className={`py-2.5 text-right font-semibold tabular-nums ${Math.abs(share) >= 5 ? (row.variance > 0 ? "text-red-600" : "text-amber-600") : ""}`}>
                    {row.variance > 0 ? "+" : ""}
                    {qty(row, row.variance)} ({share.toFixed(1)}%)
                  </td>
                  <td className="py-2.5 text-right tabular-nums">{formatMoney(row.variance_cost_cents, currency)}</td>
                </tr>
              );
            })}
            {report && report.rows.length === 0 ? (
              <tr>
                <td colSpan={7} className="py-6 text-center text-charcoal/50">
                  No dishes with recipes were sold in this period.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-charcoal/50">
        Negative variance: less used than the recipes say, or stock the kitchen did not have on the system when the dish sold.
      </p>
    </section>
  );
}
