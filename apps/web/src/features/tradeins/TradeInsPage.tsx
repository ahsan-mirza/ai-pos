import { TRADE_IN_GRADE_LABELS, formatMoney, type TradeIn, type TradeInList } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";

const iso = (value: Date) => value.toISOString().slice(0, 10);
const monthStart = () => {
  const now = new Date();
  return iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), 1)));
};

const payoutLabels: Record<TradeIn["payout"], string> = {
  CASH: "Cash",
  STORE_CREDIT: "Store credit",
  SALE_CREDIT: "Off a sale",
};

function StatusChip({ row }: { row: TradeIn }) {
  const label =
    row.status === "CANCELLED" ? "Cancelled" : row.status === "ACCEPTED" ? "Awaiting sale" : row.grade === "D" ? "In repair" : "In stock";
  const tone =
    row.status === "ACCEPTED"
      ? "bg-accent text-white"
      : row.status === "CANCELLED"
        ? "bg-white text-charcoal/40 ring-1 ring-line"
        : "bg-surface text-charcoal ring-1 ring-line";
  return <span className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${tone}`}>{label}</span>;
}

export function TradeInsPage() {
  const { currency } = useCurrency();
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(iso(new Date()));
  const [data, setData] = useState<TradeInList | null>(null);
  const [error, setError] = useState<string | null>(null);
  const money = (cents: number) => formatMoney(cents, currency);

  const load = useCallback(async () => {
    try {
      setData(await apiGet<TradeInList>(`/api/v1/trade-ins?from=${from}&to=${to}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load trade-ins."));
    }
  }, [from, to]);

  useEffect(() => {
    void load();
  }, [load]);

  const live = (data?.items ?? []).filter((row) => row.status !== "CANCELLED");
  const potential = live.reduce((sum, row) => sum + row.resale_price_cents - row.offer_cents, 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Devices bought in</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? money(data.bought_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{data?.count ?? 0} trade-ins in the period</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Margin waiting on resale</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? money(potential) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">Resale price less what was paid</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Credit not yet used</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{data ? money(data.awaiting_sale_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">Promised off a sale that has not synced yet</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Trade-ins</h2>
            <p className="text-sm text-charcoal/60">
              Used devices bought at the registers. Each one is stocked under a pre-owned SKU at the price paid.
            </p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
            <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Trade-in</th>
                <th className="pb-3 font-medium">Device</th>
                <th className="pb-3 font-medium">Seller</th>
                <th className="pb-3 text-right font-medium">Paid</th>
                <th className="pb-3 text-right font-medium">Resell at</th>
                <th className="pb-3 pl-6 font-medium">Paid as</th>
                <th className="pb-3 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {(data?.items ?? []).map((row) => (
                <tr key={row.id} className={`border-t border-line align-top ${row.status === "CANCELLED" ? "opacity-50" : ""}`}>
                  <td className="py-3">
                    <span className="block font-mono text-xs font-semibold">{row.number}</span>
                    <span className="block text-xs text-charcoal/50 tabular-nums">
                      {new Date(row.created_at).toLocaleDateString(undefined, { day: "numeric", month: "short" })} · {row.store_code} ·{" "}
                      {row.cashier_name ?? ""}
                    </span>
                  </td>
                  <td className="py-3">
                    <span className="block font-medium">{row.product_name}</span>
                    <span className="block text-xs text-charcoal/50">
                      {TRADE_IN_GRADE_LABELS[row.grade]} · {row.identifier_kind.toUpperCase()} {row.identifier_tail}
                      {row.checklist.battery_pct !== null ? ` · battery ${row.checklist.battery_pct}%` : ""}
                    </span>
                  </td>
                  <td className="py-3">
                    <span className="block">{row.seller_name}</span>
                    <span className="block text-xs text-charcoal/50">
                      {row.seller_phone} · ID …{row.seller_id_last4}
                    </span>
                  </td>
                  <td className="py-3 text-right font-semibold tabular-nums">{money(row.offer_cents)}</td>
                  <td className="py-3 text-right tabular-nums">
                    {money(row.resale_price_cents)}
                    <span className="block font-mono text-[11px] text-charcoal/50">{row.resale_sku}</span>
                  </td>
                  <td className="py-3 pl-6 text-charcoal/70">
                    {payoutLabels[row.payout]}
                    {row.store_credit_code ? <span className="block font-mono text-[11px]">{row.store_credit_code}</span> : null}
                  </td>
                  <td className="py-3">
                    <StatusChip row={row} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {data && data.items.length === 0 ? <p className="py-8 text-sm text-charcoal/60">No trade-ins in this period.</p> : null}
        </div>
      </div>
    </section>
  );
}
