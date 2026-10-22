import { formatMoney, type Shift, type ShiftStatus } from "@ai-pos/shared-types";
import { Clock } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { formatDate, storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

const methodLabels: Record<string, string> = {
  cash: "Cash",
  card: "Card",
  transfer: "Bank transfer",
  cheque: "Cheque",
  store_credit: "Store credit",
  original_card: "Card reversal",
  deposit: "Deposit",
  qr: "QR payment",
  loyalty: "Loyalty points",
  trade_in: "Trade-in credit",
  channel: "Delivery apps",
};

const movementLabels: Record<string, string> = {
  PAY_IN: "Pay-in",
  PAY_OUT: "Pay-out",
  CASH_DROP: "Safe drop",
  NO_SALE: "No-sale open",
};

function VarianceChip({ shift }: { shift: Shift }) {
  if (shift.status === "OPEN" || shift.variance_cents === null) {
    return <span className="rounded-full bg-accent px-2.5 py-0.5 text-[11px] font-semibold text-white">Open</span>;
  }
  const value = shift.variance_cents;
  const label = value === 0 ? "Balanced" : `${value > 0 ? "Over" : "Short"} ${formatMoney(Math.abs(value), shift.currency)}`;
  return (
    <span
      className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold tabular-nums ${
        value === 0 ? "bg-surface text-charcoal ring-1 ring-line" : "bg-charcoal text-white"
      }`}
    >
      {label}
    </span>
  );
}

export function ShiftsPage() {
  const { user } = useAuth();
  const { stores } = useStores();
  const [storeId, setStoreId] = useState(user?.store_id ?? "");
  const [status, setStatus] = useState<ShiftStatus | "">("");
  const [shifts, setShifts] = useState<Shift[] | null>(null);
  const [selected, setSelected] = useState<Shift | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const params = new URLSearchParams({ limit: "100" });
    if (storeId) params.set("store_id", storeId);
    if (status) params.set("status", status);
    try {
      setShifts(await apiGet<Shift[]>(`/api/v1/shifts?${params.toString()}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load shifts."));
    }
  }, [status, storeId]);

  useEffect(() => {
    void load();
  }, [load]);

  const rows = useMemo(() => shifts ?? [], [shifts]);
  const closed = rows.filter((shift) => shift.status === "CLOSED");
  const netVariance = closed.reduce((sum, shift) => sum + (shift.variance_cents ?? 0), 0);
  const currency = rows[0]?.currency ?? "AED";

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Open now</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{rows.filter((shift) => shift.status === "OPEN").length}</p>
          <p className="mt-2 text-xs text-white/50">Registers taking cash right now</p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Net drawer variance</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{formatMoney(netVariance, currency)}</p>
          <p className="mt-2 text-xs text-white/80">Across {closed.length} closed shifts listed</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Shifts with a variance</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">
            {closed.filter((shift) => (shift.variance_cents ?? 0) !== 0).length}
          </p>
          <p className="mt-2 text-xs text-charcoal/50">Counted blind at close</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Shifts</h2>
            <p className="text-sm text-charcoal/60">Opened and closed on each register, even offline. Open one for its X / Z report.</p>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-56"
              />
            )}
            <FilterSelect<ShiftStatus | "">
              label="Status"
              value={status}
              options={[
                { value: "", label: "Any status" },
                { value: "OPEN", label: "Open" },
                { value: "CLOSED", label: "Closed" },
              ]}
              onChange={setStatus}
              className="w-40"
            />
          </div>
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[860px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Shift</th>
                <th className="pb-3 font-medium">Register</th>
                <th className="pb-3 font-medium">Cashier</th>
                <th className="pb-3 font-medium">Opened</th>
                <th className="pb-3 text-right font-medium">Sales</th>
                <th className="pb-3 text-right font-medium">Expected cash</th>
                <th className="pb-3 text-right font-medium">Counted</th>
                <th className="pb-3 pl-6 font-medium">Drawer</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((shift) => (
                <tr
                  key={shift.id}
                  onClick={() => setSelected(shift)}
                  className="cursor-pointer border-t border-line transition-colors hover:bg-surface"
                >
                  <td className="py-3 font-mono text-xs">{shift.z_number ?? shift.id.slice(0, 8).toUpperCase()}</td>
                  <td className="py-3">
                    {shift.store_code}
                    {shift.device_code ? <span className="text-charcoal/50"> · {shift.device_code}</span> : null}
                  </td>
                  <td className="py-3">{shift.opened_by_name}</td>
                  <td className="py-3 text-charcoal/70">{formatDate(shift.opened_at)}</td>
                  <td className="py-3 text-right tabular-nums">{formatMoney(shift.report.sales_total_cents, shift.currency)}</td>
                  <td className="py-3 text-right tabular-nums">{formatMoney(shift.expected_cash_cents, shift.currency)}</td>
                  <td className="py-3 text-right tabular-nums">
                    {shift.counted_cash_cents === null ? "—" : formatMoney(shift.counted_cash_cents, shift.currency)}
                  </td>
                  <td className="py-3 pl-6">
                    <VarianceChip shift={shift} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {shifts !== null && rows.length === 0 ? (
            <p className="py-8 text-sm text-charcoal/60">No shifts yet. Registers open one before their first sale.</p>
          ) : null}
        </div>
      </div>
      {selected ? <ShiftReportModal shift={selected} onClose={() => setSelected(null)} /> : null}
    </section>
  );
}

function ShiftReportModal({ shift, onClose }: { shift: Shift; onClose: () => void }) {
  const money = (cents: number) => formatMoney(cents, shift.currency);
  const report = shift.report;
  const row = (label: string, value: string, strong = false) => (
    <div key={label} className={`flex justify-between gap-3 py-1.5 text-sm ${strong ? "font-semibold" : ""}`}>
      <dt className={strong ? "" : "text-charcoal/60"}>{label}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
  return (
    <Modal
      title={shift.status === "CLOSED" ? `Z report ${shift.z_number ?? ""}` : "X report (shift still open)"}
      subtitle={`${shift.store_code}${shift.device_code ? ` · ${shift.device_code}` : ""} · ${shift.opened_by_name} · ${formatDate(shift.opened_at)}${
        shift.closed_at ? ` to ${formatDate(shift.closed_at)}` : ""
      }`}
      onClose={onClose}
      width="lg"
    >
      <div className="grid gap-4 md:grid-cols-2">
        <dl className="divide-y divide-line rounded-2xl bg-surface px-4 py-2">
          {row(`Sales (${report.sales_count})`, money(report.sales_total_cents), true)}
          {Object.entries(report.tenders).map(([method, cents]) => row(methodLabels[method] ?? method, money(cents)))}
          {report.on_account_cents > 0 ? row("On account", money(report.on_account_cents)) : null}
          {row("VAT", money(report.tax_cents))}
          {report.returns_count > 0 ? row(`Refunds (${report.returns_count})`, `−${money(report.refunds_total_cents)}`) : null}
          {report.service_charge_cents ? row("Service charge", money(report.service_charge_cents)) : null}
          {report.tips_cents ? row("Tips (owed to staff)", money(report.tips_cents), true) : null}
          {(report.tips_by_server ?? []).map((server) => row(`  ${server.name}`, money(server.tips_cents)))}
        </dl>
        <dl className="divide-y divide-line rounded-2xl bg-charcoal px-4 py-2 text-white [&_dt]:text-white/60">
          {row("Opening float", money(report.opening_float_cents))}
          {row("Cash sales", money(report.tenders.cash ?? 0))}
          {report.refund_tenders.cash ? row("Cash refunds", `−${money(report.refund_tenders.cash)}`) : null}
          {report.pay_in_cents ? row("Pay-ins", money(report.pay_in_cents)) : null}
          {report.pay_out_cents ? row("Pay-outs", `−${money(report.pay_out_cents)}`) : null}
          {report.drops_cents ? row("Safe drops", `−${money(report.drops_cents)}`) : null}
          {row("Expected in drawer", money(shift.expected_cash_cents), true)}
          {shift.counted_cash_cents !== null ? row("Counted", money(shift.counted_cash_cents), true) : null}
          {Object.entries(report.foreign_cash ?? {}).map(([code, cents]) =>
            row(
              `${code} drawer`,
              `${formatMoney(cents, code)}${
                report.foreign_counted?.[code] !== undefined ? ` · counted ${formatMoney(report.foreign_counted[code] ?? 0, code)}` : ""
              }`,
            ),
          )}
          {shift.variance_cents !== null ? (
            <div className="flex justify-between py-2 text-base font-semibold">
              <dt className="!text-white">{shift.variance_cents === 0 ? "Balanced" : shift.variance_cents > 0 ? "Over" : "Short"}</dt>
              <dd className={`tabular-nums ${shift.variance_cents === 0 ? "" : "text-accent"}`}>
                {money(Math.abs(shift.variance_cents))}
              </dd>
            </div>
          ) : null}
        </dl>
      </div>
      {shift.movements.length > 0 ? (
        <>
          <h3 className="mt-6 text-xs font-semibold uppercase tracking-wider text-charcoal/50">Cash movements</h3>
          <ul className="mt-2 divide-y divide-line rounded-2xl border border-line">
            {shift.movements.map((movement) => (
              <li key={movement.id} className="flex items-center gap-3 px-4 py-2.5 text-sm">
                <Clock size={14} aria-hidden="true" className="shrink-0 text-charcoal/40" />
                <span className="min-w-0 flex-1 truncate">
                  <span className="font-semibold">{movementLabels[movement.kind] ?? movement.kind}</span>
                  {movement.reason ? ` · ${movement.reason}` : ""} · {movement.user_name}
                </span>
                <span className="shrink-0 tabular-nums">{movement.amount_cents ? money(movement.amount_cents) : "—"}</span>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </Modal>
  );
}
