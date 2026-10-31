import { formatMoney } from "@ai-pos/shared-types";
import { Ban } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

interface CancellationRow {
  order_id: string;
  number: string;
  order_type: string;
  full: boolean;
  reason_label: string;
  initiator: string;
  note: string;
  cancelled_value_cents: number;
  employee_name: string | null;
  employee_role: string | null;
  approver_id: string | null;
}

interface CancellationReport {
  created_orders: number;
  fully_cancelled: number;
  partially_cancelled: number;
  full_cancellation_rate: number;
  partial_cancellation_rate: number;
  cancelled_value_cents: number;
  customer_requested: number;
  employee_initiated: number;
  average_hours_to_cancel: number | null;
  reasons: { code: string; label: string; count: number }[];
  total: number;
  rows: CancellationRow[];
}

/** Cancellations already recorded on sales orders and open orders. These amounts are not completed sales. */
export function CancellationsPage() {
  const { user } = useAuth();
  const { currency } = useCurrency();
  const { stores } = useStores();
  const today = useMemo(() => new Date(), []);
  const [range, setRange] = useState(() => ({
    from: iso(new Date(today.getFullYear(), today.getMonth(), 1)),
    to: iso(today),
  }));
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [report, setReport] = useState<CancellationReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const query = useMemo(() => {
    const params = new URLSearchParams({ from: range.from, to: range.to });
    if (storeId) params.set("store_id", storeId);
    return params.toString();
  }, [range, storeId]);

  const load = useCallback(async () => {
    try {
      setReport(await apiGet<CancellationReport>(`/api/v1/reports/cancellations?${query}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load cancellations."));
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const money = (cents: number) => formatMoney(cents, currency);
  const cards = [
    ["Orders created", String(report?.created_orders ?? 0)],
    ["Fully cancelled", String(report?.fully_cancelled ?? 0)],
    ["Partly cancelled", String(report?.partially_cancelled ?? 0)],
    ["Full-order rate", `${report?.full_cancellation_rate ?? 0}%`],
    ["Partial rate", `${report?.partial_cancellation_rate ?? 0}%`],
    ["Cancelled value", money(report?.cancelled_value_cents ?? 0)],
    ["Customer requested", String(report?.customer_requested ?? 0)],
    ["Employee initiated", String(report?.employee_initiated ?? 0)],
  ];

  return (
    <section className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Ban size={22} /> Cancellations
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Full-order rate is fully cancelled orders divided by orders created in this range. Partial cancellations are
            counted on their own and are not treated as completed sales.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <TextField label="From" type="date" value={range.from} onChange={(event) => setRange({ ...range, from: event.target.value })} />
          <TextField label="To" type="date" value={range.to} onChange={(event) => setRange({ ...range, to: event.target.value })} />
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
      </header>
      <ErrorNote message={error} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {cards.map(([label, value]) => (
          <article key={label} className="rounded-2xl border border-line bg-white p-4">
            <p className="text-xs font-medium uppercase tracking-wide text-ink-soft">{label}</p>
            <p className="mt-1 text-xl font-semibold">{value}</p>
          </article>
        ))}
      </div>
      {report && report.average_hours_to_cancel != null ? (
        <p className="text-sm text-ink-soft">Average time from order to cancellation: {report.average_hours_to_cancel} hours.</p>
      ) : null}
      <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <ul className="space-y-2 rounded-2xl border border-line bg-white p-4">
          {(report?.reasons ?? []).map((reason) => (
            <li key={reason.code} className="flex justify-between gap-3 text-sm">
              <span>{reason.label}</span>
              <span className="font-semibold">{reason.count}</span>
            </li>
          ))}
          {report && report.reasons.length === 0 ? <li className="text-sm text-ink-soft">No cancellations in this range.</li> : null}
        </ul>
        <div className="overflow-x-auto rounded-2xl border border-line bg-white">
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-ink-soft">
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Reason</th>
                <th className="px-4 py-3">Started by</th>
                <th className="px-4 py-3">Employee</th>
                <th className="px-4 py-3 text-right">Value</th>
              </tr>
            </thead>
            <tbody>
              {(report?.rows ?? []).map((row) => (
                <tr key={row.order_id} className="border-t border-line">
                  <td className="px-4 py-3 font-medium">{row.number}</td>
                  <td className="px-4 py-3">{row.full ? "Cancelled" : "Partially cancelled"}</td>
                  <td className="px-4 py-3">
                    {row.reason_label}
                    {row.note ? <span className="block text-ink-soft">{row.note}</span> : null}
                  </td>
                  <td className="px-4 py-3 capitalize">{row.initiator}</td>
                  <td className="px-4 py-3">
                    {row.employee_name ?? "—"}
                    {row.employee_role ? <span className="block text-ink-soft">{row.employee_role}</span> : null}
                    {row.approver_id ? <span className="block text-ink-soft">Manager approved</span> : null}
                  </td>
                  <td className="px-4 py-3 text-right">{money(row.cancelled_value_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {report && report.total > report.rows.length ? (
            <p className="px-4 py-3 text-sm text-ink-soft">Showing {report.rows.length} of {report.total}.</p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
