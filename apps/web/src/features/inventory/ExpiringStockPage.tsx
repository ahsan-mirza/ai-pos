import { formatMoney, type ExpiringStockRow } from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote } from "../../components/ui/Field";
import { SegmentedControl } from "../../components/ui/SegmentedControl";
import { apiGet, apiPost } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";

const ranges = [
  { value: "default", label: "Alert window" },
  { value: "30", label: "30 days" },
  { value: "90", label: "90 days" },
] as const;

const shortDate = (value: string) =>
  new Date(`${value}T00:00:00`).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });

function DaysLeft({ row }: { row: ExpiringStockRow }) {
  if (row.expired) {
    return <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-white">Expired {-row.days_left}d ago</span>;
  }
  const tone = row.days_left <= 3 ? "bg-warning/10 text-warning" : "bg-charcoal/5 text-charcoal/70";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${tone}`}>{row.days_left === 0 ? "Today" : `${row.days_left}d left`}</span>;
}

/** Expiry-first stock: batches past or near their expiry, with a write-off for what can no longer be sold. */
export function ExpiringStockPage() {
  const { currency } = useCurrency();
  const [range, setRange] = useState<(typeof ranges)[number]["value"]>("default");
  const [rows, setRows] = useState<ExpiringStockRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      const query = range === "default" ? "" : `?days=${range}`;
      setRows(await apiGet<ExpiringStockRow[]>(`/api/v1/inventory/expiring${query}`));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load expiring stock."));
    }
  }, [range]);

  useEffect(() => {
    void load();
  }, [load]);

  async function writeOff(row: ExpiringStockRow) {
    const accepted = await confirm({
      title: "Write off stock",
      message: `Write off ${row.quantity_remaining} × ${row.product_name} (batch ${row.batch_number})?`,
      confirmLabel: "Write off",
      tone: "danger",
    });
    if (!accepted) return;
    setBusy(row.batch_item_id);
    try {
      await apiPost("/api/v1/inventory/expiry-writeoff", { batch_item_id: row.batch_item_id });
      await load();
    } catch (caught) {
      setError(message(caught, "Could not write the batch off."));
    } finally {
      setBusy(null);
    }
  }

  const expired = (rows ?? []).filter((row) => row.expired);
  const soon = (rows ?? []).filter((row) => !row.expired);
  const value = (list: ExpiringStockRow[]) => list.reduce((sum, row) => sum + row.value_cents, 0);

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Expired, still on hand</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{rows ? expired.length : "—"}</p>
          <p className="mt-2 text-xs text-white/80">{rows ? `${formatMoney(value(expired), currency)} at cost` : "Batch lines"}</p>
        </article>
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Expiring soon</p>
          <p className="mt-4 text-3xl font-semibold tabular-nums">{rows ? soon.length : "—"}</p>
          <p className="mt-2 text-xs text-white/50">{rows ? `${formatMoney(value(soon), currency)} at cost` : "Batch lines"}</p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">How registers sell</p>
          <p className="mt-4 text-lg font-semibold">Soonest expiry first</p>
          <p className="mt-2 text-xs text-charcoal/50">Expired batches are only drawn once nothing fresher is left.</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold">Expiring stock</h2>
            <p className="text-sm text-charcoal/60">Batch lines with an expiry date inside the window, soonest first.</p>
          </div>
          <SegmentedControl label="Window" value={range} options={ranges} onChange={setRange} />
        </div>
        <ErrorNote message={error} />
        <div className="overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Product</th>
                <th className="pb-3 font-medium">Batch</th>
                <th className="pb-3 font-medium">Expiry</th>
                <th className="pb-3 text-right font-medium">On hand</th>
                <th className="pb-3 text-right font-medium">Value at cost</th>
                <th className="pb-3" />
              </tr>
            </thead>
            <tbody>
              {(rows ?? []).map((row) => (
                <tr key={row.batch_item_id} className="border-t border-line align-middle">
                  <td className="py-3">
                    <span className="block font-semibold">{row.product_name}</span>
                    <span className="block font-mono text-xs text-charcoal/50">{row.sku}</span>
                  </td>
                  <td className="py-3">
                    <span className="block font-mono text-xs">{row.batch_number}</span>
                    <span className="block text-xs text-charcoal/50">{row.store_code}</span>
                  </td>
                  <td className="py-3">
                    <span className="mr-2 tabular-nums">{shortDate(row.expiry_date)}</span>
                    <DaysLeft row={row} />
                  </td>
                  <td className="py-3 text-right tabular-nums">{row.quantity_remaining}</td>
                  <td className="py-3 text-right tabular-nums">{formatMoney(row.value_cents, currency)}</td>
                  <td className="py-3 text-right">
                    {row.expired ? (
                      <button
                        type="button"
                        disabled={busy !== null}
                        onClick={() => void writeOff(row)}
                        className="rounded-full border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent hover:text-white disabled:opacity-40"
                      >
                        {busy === row.batch_item_id ? "Writing off…" : "Write off"}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows !== null && rows.length === 0 ? <p className="py-8 text-sm text-charcoal/60">Nothing expires inside this window.</p> : null}
        </div>
      </div>
    </section>
  );
}
