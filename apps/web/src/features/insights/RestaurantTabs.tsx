import { formatMoney, type KitchenReport, type TableReport, type UpsellReport } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { ErrorNote } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { errorMessage } from "../users/api";

const REFRESH_MS = 60_000;

function useLive<T>(path: string, failure: string, refreshMs = 0) {
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
    if (!refreshMs) return;
    const timer = window.setInterval(() => void load(), refreshMs);
    return () => window.clearInterval(timer);
  }, [load, refreshMs]);
  return { data, error };
}

const minutes = (value: number | null) => (value === null ? "—" : `${value.toFixed(value < 10 ? 1 : 0)} min`);
const hourLabel = (hour: number) => `${String(hour).padStart(2, "0")}:00`;

function Empty({ text }: { text: string }) {
  return <p className="rounded-card border border-line bg-white p-6 text-sm text-charcoal/60">{text}</p>;
}

/** Prep times per station with a fitted model, the wait a new ticket faces, and tickets likely to run late. */
export function KitchenTab() {
  const { data, error } = useLive<KitchenReport>("/api/v1/insights/kitchen", "Could not load the kitchen.", REFRESH_MS);
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  if (data.stations.length === 0) return <Empty text="No kitchen stations yet. Add them under Inventory → Kitchen stations." />;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {data.stations.map((station) => (
        <article key={station.station_id} className="rounded-card border border-line bg-white p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h3 className="text-base font-semibold">{station.station_name}</h3>
              <p className="text-xs text-charcoal/60">
                {station.store_code} · {station.tickets_28d} tickets in 28 days
                {station.busiest_hours.length ? ` · busiest ${station.busiest_hours.map(hourLabel).join(", ")}` : ""}
              </p>
            </div>
            <span className="text-right">
              <span className="block text-[11px] uppercase tracking-wider text-charcoal/50">New ticket now</span>
              <span className="block text-xl font-semibold tabular-nums">{minutes(station.wait_now_minutes)}</span>
            </span>
          </div>
          <dl className="mt-4 grid grid-cols-3 gap-2 text-sm">
            <div className="rounded-2xl bg-surface p-3">
              <dt className="text-[11px] text-charcoal/60">Median</dt>
              <dd className="font-semibold tabular-nums">{minutes(station.median_minutes)}</dd>
            </div>
            <div className="rounded-2xl bg-surface p-3">
              <dt className="text-[11px] text-charcoal/60">Slowest 10%</dt>
              <dd className="font-semibold tabular-nums">{minutes(station.p90_minutes)}</dd>
            </div>
            <div className="rounded-2xl bg-surface p-3">
              <dt className="text-[11px] text-charcoal/60">Over {data.late_minutes} min</dt>
              <dd className={`font-semibold tabular-nums ${station.late_share_bps > 1500 ? "text-red-600" : ""}`}>
                {(station.late_share_bps / 100).toFixed(0)}%
              </dd>
            </div>
          </dl>
          {station.model ? (
            <p className="mt-3 text-xs text-charcoal/60">
              Each ticket takes about {station.model.base_minutes.toFixed(1)} min, plus{" "}
              {station.model.per_item_minutes.toFixed(1)} per item and {station.model.per_queued_minutes.toFixed(1)} per
              ticket already waiting. Off by {station.model.mae_minutes.toFixed(1)} min on average, against{" "}
              {station.model.baseline_mae_minutes.toFixed(1)} for a flat guess ({station.model.samples} tickets).
            </p>
          ) : (
            <p className="mt-3 text-xs text-charcoal/60">Needs 20 finished tickets before it predicts per ticket.</p>
          )}
          {station.live.length ? (
            <ul className="mt-3 space-y-1.5">
              {station.live.map((ticket) => (
                <li
                  key={ticket.ticket_id}
                  className={`flex items-center justify-between rounded-xl px-3 py-2 text-sm ${
                    ticket.at_risk ? "bg-red-50 text-red-800" : "bg-surface"
                  }`}
                >
                  <span>
                    #{ticket.number} · {ticket.label} · {ticket.items} item{ticket.items === 1 ? "" : "s"}
                  </span>
                  <span className="tabular-nums">
                    {minutes(ticket.elapsed_minutes)} in
                    {ticket.at_risk ? " · running late" : ` · ~${minutes(ticket.remaining_minutes)} left`}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-xs text-charcoal/50">Nothing on the pass right now.</p>
          )}
        </article>
      ))}
    </div>
  );
}

/** How long tables are held, which earn most per hour, and when the open ones should free up. */
export function TablesTab() {
  const { data, error } = useLive<TableReport>("/api/v1/insights/tables", "Could not load tables.", REFRESH_MS);
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  if (data.dine_in_orders === 0 && data.open_tables.length === 0) {
    return <Empty text="No dine-in orders on tables in the last 28 days yet." />;
  }
  const money = (cents: number) => formatMoney(cents, data.currency);
  const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return (
    <>
      <article className="rounded-card border border-line bg-white p-5">
        <h3 className="text-base font-semibold">Time at the table</h3>
        <p className="text-xs text-charcoal/60">
          Median {minutes(data.median_minutes)} over {data.dine_in_orders} dine-in orders in {data.days} days.
        </p>
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          {[
            ["By party size", data.by_party],
            ["By time of day", data.by_daypart],
          ].map(([title, rows]) => (
            <div key={title as string}>
              <p className="text-xs font-semibold uppercase tracking-wide text-charcoal/50">{title as string}</p>
              <ul className="mt-2 space-y-1.5 text-sm">
                {(rows as TableReport["by_party"]).map((row) => (
                  <li key={row.label} className="flex justify-between rounded-xl bg-surface px-3 py-2">
                    <span>
                      {row.label} <span className="text-xs text-charcoal/50">· {row.orders} orders</span>
                    </span>
                    <span className="tabular-nums">
                      {minutes(row.median_minutes)} <span className="text-xs text-charcoal/50">(slowest 10%: {minutes(row.p90_minutes)})</span>
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </article>
      {data.open_tables.length ? (
        <article className="rounded-card border border-line bg-white p-5">
          <h3 className="text-base font-semibold">Open tables</h3>
          <ul className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {data.open_tables.map((row) => (
              <li key={row.order_id} className={`rounded-2xl p-3 text-sm ${row.lingering ? "bg-amber-50 text-amber-900" : "bg-surface"}`}>
                <span className="block font-semibold">
                  {row.label} · {row.covers} guest{row.covers === 1 ? "" : "s"}
                </span>
                <span className="block text-xs">
                  Seated {minutes(row.elapsed_minutes)} · usually {minutes(row.expected_minutes)} ·{" "}
                  {row.lingering ? "running long" : `free about ${time(row.predicted_free_at)}`}
                </span>
              </li>
            ))}
          </ul>
        </article>
      ) : null}
      <article className="overflow-x-auto rounded-card border border-line bg-white p-5">
        <h3 className="text-base font-semibold">Tables by revenue per hour</h3>
        <table className="mt-3 w-full min-w-[640px] text-left text-sm">
          <thead className="text-xs uppercase tracking-wide text-charcoal/50">
            <tr>
              <th className="pb-2 font-medium">Table</th>
              <th className="pb-2 text-right font-medium">Seats</th>
              <th className="pb-2 text-right font-medium">Turns / day</th>
              <th className="pb-2 text-right font-medium">Median stay</th>
              <th className="pb-2 text-right font-medium">Revenue</th>
              <th className="pb-2 text-right font-medium">Per hour</th>
            </tr>
          </thead>
          <tbody>
            {data.tables.map((row) => (
              <tr key={row.table_id} className="border-t border-line">
                <td className="py-2 font-medium">
                  {row.label} <span className="text-xs text-charcoal/50">{row.store_code}</span>
                </td>
                <td className="py-2 text-right tabular-nums">{row.seats}</td>
                <td className="py-2 text-right tabular-nums">{row.turns_per_day}</td>
                <td className="py-2 text-right tabular-nums">{minutes(row.median_minutes)}</td>
                <td className="py-2 text-right tabular-nums">{money(row.revenue_cents)}</td>
                <td className="py-2 text-right font-semibold tabular-nums">{money(row.revenue_per_hour_cents)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </article>
    </>
  );
}

/** Items guests order together: prompts for waiters and candidates for combos. */
export function UpsellTab() {
  const { data, error } = useLive<UpsellReport>("/api/v1/insights/upsell?limit=40", "Could not load pairs.");
  if (!data) return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading…</p>;
  if (data.pairs.length === 0) {
    return <Empty text={`No strong pairs in ${data.baskets} orders over ${data.days} days yet. They appear once items are often ordered together.`} />;
  }
  return (
    <article className="overflow-x-auto rounded-card border border-line bg-white p-5">
      <h3 className="text-base font-semibold">Ordered together</h3>
      <p className="text-xs text-charcoal/60">
        From {data.baskets} orders in {data.days} days. “Takes it” is how often the add-on joins the first item; “lift”
        is how much likelier that is than chance. Strong pairs make good waiter prompts and combo deals.
      </p>
      <table className="mt-3 w-full min-w-[720px] text-left text-sm">
        <thead className="text-xs uppercase tracking-wide text-charcoal/50">
          <tr>
            <th className="pb-2 font-medium">When they order</th>
            <th className="pb-2 font-medium">Suggest</th>
            <th className="pb-2 text-right font-medium">Takes it</th>
            <th className="pb-2 text-right font-medium">Lift</th>
            <th className="pb-2 text-right font-medium">Orders together</th>
          </tr>
        </thead>
        <tbody>
          {data.pairs.map((pair) => (
            <tr key={`${pair.product_id}-${pair.add_on_id}`} className="border-t border-line">
              <td className="py-2 font-medium">{pair.product_name}</td>
              <td className="py-2">
                {pair.add_on_name}{" "}
                <span className="text-xs text-charcoal/50">{formatMoney(pair.add_on_price_cents, data.currency)}</span>
              </td>
              <td className="py-2 text-right tabular-nums">{(pair.confidence_bps / 100).toFixed(0)}%</td>
              <td className="py-2 text-right tabular-nums">{pair.lift.toFixed(1)}×</td>
              <td className="py-2 text-right tabular-nums">{pair.together}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </article>
  );
}
