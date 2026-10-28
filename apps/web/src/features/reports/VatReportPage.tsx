import { formatMoney, type VatReport } from "@ai-pos/shared-types";
import { Download, FileText, Landmark } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, FilterSelect, TextField } from "../../components/ui/Field";
import { apiBlob, apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useCurrency } from "../../lib/currency";
import { storeOptions, useStores } from "../inventory/shared";
import { errorMessage } from "../users/api";

type Period = "this_quarter" | "last_quarter" | "this_month" | "last_month" | "custom";

const iso = (value: Date) =>
  `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;

/** UAE VAT periods are usually calendar quarters; months are offered for monthly filers. */
function periodRange(period: Exclude<Period, "custom">, today = new Date()): { from: string; to: string } {
  const year = today.getFullYear();
  const month = today.getMonth();
  if (period === "this_month" || period === "last_month") {
    const start = new Date(year, month - (period === "last_month" ? 1 : 0), 1);
    return { from: iso(start), to: iso(new Date(start.getFullYear(), start.getMonth() + 1, 0)) };
  }
  const quarterStart = month - (month % 3) - (period === "last_quarter" ? 3 : 0);
  const start = new Date(year, quarterStart, 1);
  return { from: iso(start), to: iso(new Date(start.getFullYear(), start.getMonth() + 3, 0)) };
}

const periodOptions: { value: Period; label: string }[] = [
  { value: "this_quarter", label: "This quarter" },
  { value: "last_quarter", label: "Last quarter" },
  { value: "this_month", label: "This month" },
  { value: "last_month", label: "Last month" },
  { value: "custom", label: "Custom range" },
];

export function VatReportPage() {
  const { currency: businessCurrency } = useCurrency();
  const { user } = useAuth();
  const { stores } = useStores();
  const [period, setPeriod] = useState<Period>("this_quarter");
  const [range, setRange] = useState(() => periodRange("this_quarter"));
  const [storeId, setStoreId] = useState<string>(user?.store_id ?? "");
  const [report, setReport] = useState<VatReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const query = useMemo(() => {
    const params = new URLSearchParams({ from: range.from, to: range.to });
    if (storeId) params.set("store_id", storeId);
    return params.toString();
  }, [range, storeId]);

  const load = useCallback(async () => {
    setBusy(true);
    try {
      setReport(await apiGet<VatReport>(`/api/v1/reports/vat?${query}`));
      setError(null);
    } catch (caught) {
      setError(errorMessage(caught, "Could not build the VAT report."));
    } finally {
      setBusy(false);
    }
  }, [query]);

  useEffect(() => {
    void load();
  }, [load]);

  const download = async (format: "csv" | "pdf") => {
    try {
      const blob = await apiBlob(`/api/v1/reports/vat/export?${query}&format=${format}`);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `vat-${range.from}-${range.to}.${format}`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (caught) {
      setError(errorMessage(caught, "Could not export the VAT report."));
    }
  };

  const money = (cents: number) => formatMoney(cents, report?.currency ?? businessCurrency);
  const emirateRows = report?.emirates.filter((row) => row.amount_cents !== 0 || row.vat_cents !== 0 || row.adjustment_cents !== 0) ?? [];

  return (
    <section className="space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <article className="rounded-card bg-charcoal p-6 text-white">
          <p className="text-sm text-white/60">Output VAT</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? money(report.output_vat_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/50">
            {report ? `${report.invoices} invoices · ${report.credit_notes} credit notes` : "Loading…"}
          </p>
        </article>
        <article className="rounded-card border border-line bg-white p-6">
          <p className="text-sm text-charcoal/60">Recoverable input VAT</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? money(report.input_vat_cents) : "—"}</p>
          <p className="mt-2 text-xs text-charcoal/50">
            {report?.input_vat_estimated ? "Estimated from goods receipts" : "From goods receipts in the period"}
          </p>
        </article>
        <article className="rounded-card bg-accent p-6 text-white">
          <p className="text-sm text-white/80">Net VAT payable</p>
          <p className="mt-4 text-4xl font-semibold tabular-nums">{report ? money(report.net_vat_cents) : "—"}</p>
          <p className="mt-2 text-xs text-white/80">Box 14 · {report?.trn ? `TRN ${report.trn}` : "No TRN on file"}</p>
        </article>
      </div>

      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-charcoal text-white">
              <Landmark size={18} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">VAT return (VAT201)</h2>
              <p className="text-sm text-charcoal/60">
                Working figures for EmaraTax. Credit notes reduce the period they are issued in.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <FilterSelect<Period>
              label="Period"
              value={period}
              options={periodOptions}
              onChange={(next) => {
                setPeriod(next);
                if (next !== "custom") setRange(periodRange(next));
              }}
              className="w-44"
            />
            {period === "custom" ? (
              <>
                <TextField
                  label="From"
                  type="date"
                  value={range.from}
                  onChange={(event) => setRange((current) => ({ ...current, from: event.target.value }))}
                />
                <TextField
                  label="To"
                  type="date"
                  value={range.to}
                  onChange={(event) => setRange((current) => ({ ...current, to: event.target.value }))}
                />
              </>
            ) : null}
            {user?.store_id ? null : (
              <FilterSelect
                label="Branch"
                value={storeId}
                options={[{ value: "", label: "All branches" }, ...storeOptions(stores)]}
                onChange={setStoreId}
                className="w-56"
              />
            )}
            <button
              type="button"
              onClick={() => void download("csv")}
              className="inline-flex h-11 items-center gap-2 rounded-full border border-line px-4 text-sm font-semibold hover:border-accent hover:text-accent"
            >
              <Download size={15} aria-hidden="true" /> CSV
            </button>
            <button
              type="button"
              onClick={() => void download("pdf")}
              className="inline-flex h-11 items-center gap-2 rounded-full bg-charcoal px-4 text-sm font-semibold text-white hover:bg-charcoal/90"
            >
              <FileText size={15} aria-hidden="true" /> PDF
            </button>
          </div>
        </div>
        <ErrorNote message={error} />
        {report && !report.vat_registered ? (
          <p className="mb-4 rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
            The business is not VAT registered in Settings, so registers' tax is accepted as sent.
          </p>
        ) : null}
        <div className={`overflow-x-auto ${busy ? "opacity-60" : ""}`}>
          <table className="w-full min-w-[720px] text-left text-sm">
            <thead className="text-xs uppercase tracking-wide text-charcoal/50">
              <tr>
                <th className="pb-3 font-medium">Box</th>
                <th className="pb-3 font-medium">Description</th>
                <th className="pb-3 text-right font-medium">Amount</th>
                <th className="pb-3 text-right font-medium">VAT</th>
                <th className="pb-3 text-right font-medium">Adjustment</th>
              </tr>
            </thead>
            <tbody>
              {emirateRows.map((row) => (
                <tr key={row.emirate ?? "unset"} className="border-t border-line">
                  <td className="py-3 font-mono text-xs">1{row.emirate ? ` · ${row.emirate}` : ""}</td>
                  <td className="py-3">Standard rated supplies in {row.label}</td>
                  <td className="py-3 text-right tabular-nums">{money(row.amount_cents)}</td>
                  <td className="py-3 text-right tabular-nums">{money(row.vat_cents)}</td>
                  <td className="py-3 text-right tabular-nums text-charcoal/60">{money(row.adjustment_cents)}</td>
                </tr>
              ))}
              {report?.boxes.map((box) => {
                const total = box.key === "8" || box.key === "11";
                return (
                  <tr key={box.key} className={`border-t border-line ${total ? "bg-surface font-semibold" : ""}`}>
                    <td className="py-3 pl-1 font-mono text-xs">{box.key}</td>
                    <td className="py-3">{box.label}</td>
                    <td className="py-3 text-right tabular-nums">{money(box.amount_cents)}</td>
                    <td className="py-3 text-right tabular-nums">{money(box.vat_cents)}</td>
                    <td className="py-3" />
                  </tr>
                );
              })}
              {report ? (
                <tr className="border-t-2 border-charcoal font-semibold">
                  <td className="py-3 font-mono text-xs">14</td>
                  <td className="py-3">Payable tax for the period</td>
                  <td className="py-3" />
                  <td className="py-3 text-right tabular-nums text-accent">{money(report.net_vat_cents)}</td>
                  <td className="py-3" />
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {report ? (
          <p className="mt-4 text-xs text-charcoal/50">
            {report.full_invoices} full and {report.simplified_invoices} simplified tax invoices. A buyer with a TRN or a
            sale over AED 10,000 gets a full tax invoice.
          </p>
        ) : null}
      </div>
    </section>
  );
}
