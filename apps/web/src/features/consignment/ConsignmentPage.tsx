import { formatMoney, type ConsignmentOverview, type ConsignmentSettlement, type ConsignmentSupplier } from "@ai-pos/shared-types";
import { ChevronDown, Handshake } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorNote, PrimaryButton } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

/** Supplier-owned stock: what is on the shelves, what sold, and settling sold units into a supplier bill. */
export function ConsignmentPage() {
  const [overview, setOverview] = useState<ConsignmentOverview | null>(null);
  const [history, setHistory] = useState<ConsignmentSettlement[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [next, settled] = await Promise.all([
        apiGet<ConsignmentOverview>("/api/v1/consignment"),
        apiGet<ConsignmentSettlement[]>("/api/v1/consignment/settlements?limit=20"),
      ]);
      setOverview(next);
      setHistory(settled);
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not load consignment stock."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const settle = async (supplier: ConsignmentSupplier) => {
    if (!window.confirm(`Raise a bill to ${supplier.supplier_name} for ${supplier.unsettled_units} sold units?`)) return;
    setBusy(supplier.supplier_id);
    setNotice(null);
    try {
      const created = await apiPost<ConsignmentSettlement[]>("/api/v1/consignment/settlements", {
        supplier_id: supplier.supplier_id,
      });
      setNotice(
        created
          .map((row) => `${row.number}: ${row.units} units, bill ${formatMoney(row.bill_total_cents, overview?.currency ?? "USD")} (${row.store_code})`)
          .join(" · "),
      );
      await load();
    } catch (caught) {
      setError(errorMessage(caught, "Could not settle with the supplier."));
    } finally {
      setBusy(null);
    }
  };

  if (overview === null) {
    return error ? <ErrorNote message={error} /> : <p className="text-sm text-charcoal/60">Loading consignment stock…</p>;
  }
  const money = (cents: number) => formatMoney(cents, overview.currency);

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
            <Handshake size={20} aria-hidden="true" />
          </span>
          <div>
            <h2 className="text-2xl font-semibold">Consignment stock</h2>
            <p className="text-sm text-charcoal/60">
              Suppliers own these units until they sell. Settle sold units into a supplier bill; Payables pays it.
            </p>
          </div>
        </div>
        <dl className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-2xl bg-charcoal p-4 text-white">
            <dt className="text-xs text-white/60">Owed for units sold, not yet settled</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{money(overview.unsettled_cents)}</dd>
          </div>
          <div className="rounded-2xl bg-surface p-4">
            <dt className="text-xs text-charcoal/60">Supplier-owned units on the shelves</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{overview.units_on_hand.toLocaleString()}</dd>
          </div>
          <div className="rounded-2xl bg-surface p-4">
            <dt className="text-xs text-charcoal/60">Their value at consignment cost</dt>
            <dd className="mt-1 text-2xl font-semibold tabular-nums">{money(overview.value_on_hand_cents)}</dd>
          </div>
        </dl>
        {notice ? <p role="status" className="mt-4 rounded-2xl bg-surface px-4 py-3 text-sm">{notice}</p> : null}
        <ErrorNote message={error} />
      </div>

      {overview.suppliers.length === 0 ? (
        <p className="rounded-card border border-line bg-white p-6 text-sm text-charcoal/60">
          No consignment stock yet. Import a purchase file with “Consignment stock” switched on to receive it.
        </p>
      ) : null}

      {overview.suppliers.map((supplier) => {
        const expanded = open === supplier.supplier_id;
        return (
          <article key={supplier.supplier_id} className="rounded-card border border-line bg-white p-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : supplier.supplier_id)}
                className="flex min-w-0 items-center gap-2 text-left"
              >
                <ChevronDown size={16} aria-hidden="true" className={`transition ${expanded ? "rotate-180" : ""}`} />
                <span>
                  <span className="block text-lg font-semibold">{supplier.supplier_name}</span>
                  <span className="block text-xs text-charcoal/60">
                    {supplier.batches} batch{supplier.batches === 1 ? "" : "es"} · {supplier.units_on_hand} on hand ·{" "}
                    {supplier.units_sold} sold · settled {money(supplier.settled_cents)}
                  </span>
                </span>
              </button>
              <div className="flex items-center gap-3">
                <span className="text-right">
                  <span className="block text-[11px] uppercase tracking-wider text-charcoal/50">To settle</span>
                  <span className="block text-lg font-semibold tabular-nums">
                    {supplier.unsettled_units} units · {money(supplier.unsettled_cents)}
                  </span>
                </span>
                <PrimaryButton disabled={supplier.unsettled_units === 0 || busy !== null} onClick={() => void settle(supplier)}>
                  {busy === supplier.supplier_id ? "Settling…" : "Settle"}
                </PrimaryButton>
              </div>
            </div>
            {expanded ? (
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[760px] text-left text-sm">
                  <thead className="text-xs uppercase tracking-wide text-charcoal/50">
                    <tr>
                      <th className="pb-2 font-medium">Product</th>
                      <th className="pb-2 font-medium">Batch</th>
                      <th className="pb-2 text-right font-medium">Received</th>
                      <th className="pb-2 text-right font-medium">On hand</th>
                      <th className="pb-2 text-right font-medium">Sold</th>
                      <th className="pb-2 text-right font-medium">Settled</th>
                      <th className="pb-2 text-right font-medium">To settle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {supplier.items.map((item) => (
                      <tr key={item.batch_item_id} className="border-t border-line">
                        <td className="py-2">
                          <span className="block font-medium">{item.name}</span>
                          <span className="block font-mono text-[11px] text-charcoal/50">{item.sku}</span>
                        </td>
                        <td className="py-2 text-xs">
                          {item.batch_number} · {item.store_code}
                        </td>
                        <td className="py-2 text-right tabular-nums">{item.received}</td>
                        <td className="py-2 text-right tabular-nums">{item.on_hand}</td>
                        <td className="py-2 text-right tabular-nums">{item.sold}</td>
                        <td className="py-2 text-right tabular-nums">{item.settled}</td>
                        <td className="py-2 text-right font-semibold tabular-nums">
                          {item.unsettled} · {money(item.unsettled_cents)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </article>
        );
      })}

      {history.length > 0 ? (
        <article className="rounded-card border border-line bg-white p-5">
          <h3 className="text-base font-semibold">Settlements</h3>
          <table className="mt-3 w-full text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-2 font-medium">Number</th>
                <th className="pb-2 font-medium">Supplier</th>
                <th className="pb-2 font-medium">Branch</th>
                <th className="pb-2 text-right font-medium">Units</th>
                <th className="pb-2 text-right font-medium">Bill</th>
                <th className="pb-2 pl-4 font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {history.map((row) => (
                <tr key={row.id} className="border-t border-line">
                  <td className="py-2 font-mono text-xs">{row.number}</td>
                  <td className="py-2">{row.supplier_name}</td>
                  <td className="py-2">{row.store_code}</td>
                  <td className="py-2 text-right tabular-nums">{row.units}</td>
                  <td className="py-2 text-right tabular-nums">{money(row.bill_total_cents)}</td>
                  <td className="py-2 pl-4">
                    <Link to="/payables" className="text-xs font-semibold text-accent hover:underline">
                      {row.bill_status.toLowerCase()} in Payables
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      ) : null}
    </section>
  );
}
