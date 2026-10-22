import { formatMoney, type ImportOptions, type ImportPreview, type ImportPreviewRow } from "@ai-pos/shared-types";
import { AlertTriangle, Info, RefreshCw, Smartphone, Sparkles } from "lucide-react";
import { useState } from "react";
import { Toggle } from "../../../components/ui/Toggle";
import { centsInput, parseCents } from "./api";
import { CostDelta, Metric, RowBadge } from "./WizardParts";

type Filter = "all" | "NEW" | "EXISTING" | "ERROR" | "excluded";

const cell =
  "h-9 w-full rounded-lg border border-transparent bg-transparent px-2 text-sm transition-colors hover:border-line focus:border-accent focus:bg-white focus:outline-none";

function MoneyCell({
  value,
  onChange,
  label,
  invalid,
}: {
  value: number | null;
  onChange: (cents: number | null) => void;
  label: string;
  invalid: boolean;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  return (
    <input
      aria-label={label}
      inputMode="decimal"
      value={draft ?? centsInput(value)}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={() => {
        if (draft !== null) onChange(parseCents(draft));
        setDraft(null);
      }}
      className={`${cell} text-right tabular-nums ${invalid ? "border-accent/50 bg-accent/[0.04]" : ""}`}
    />
  );
}

export function PreviewStep({
  preview,
  rows,
  onRow,
  dirty,
  rechecking,
  onRecheck,
  options,
  onOptions,
  notes,
  onNotes,
}: {
  preview: ImportPreview;
  rows: ImportPreviewRow[];
  onRow: (rowNumber: number, patch: Partial<ImportPreviewRow>) => void;
  dirty: boolean;
  rechecking: boolean;
  onRecheck: () => void;
  options: ImportOptions;
  onOptions: (options: ImportOptions) => void;
  notes: string;
  onNotes: (notes: string) => void;
}) {
  const [filter, setFilter] = useState<Filter>("all");
  const currency = preview.currency;
  const totals = preview.totals;
  const included = rows.filter((row) => row.include);
  const units = included.reduce((sum, row) => sum + (row.quantity ?? 0), 0);
  const cost = included.reduce((sum, row) => sum + (row.quantity ?? 0) * (row.cost_cents ?? 0), 0);
  const retail = included.reduce((sum, row) => sum + (row.quantity ?? 0) * (row.price_cents ?? 0), 0);
  const errors = included.filter((row) => row.status === "ERROR").length;
  const priceChanges = included.filter(
    (row) =>
      row.status === "EXISTING" && row.price_cents !== null && row.existing_price_cents !== row.price_cents,
  ).length;
  const visible = rows.filter((row) =>
    filter === "all" ? true : filter === "excluded" ? !row.include : row.include && row.status === filter,
  );
  const chips: { id: Filter; label: string; count: number }[] = [
    { id: "all", label: "All rows", count: rows.length },
    { id: "NEW", label: "New", count: included.filter((row) => row.status === "NEW").length },
    { id: "EXISTING", label: "Existing", count: included.filter((row) => row.status === "EXISTING").length },
    { id: "ERROR", label: "Errors", count: errors },
    { id: "excluded", label: "Excluded", count: rows.length - included.length },
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <Metric label="Lines" value={`${included.length} / ${totals.rows}`} />
        <Metric label="New products" value={chips[1]!.count} tone={chips[1]!.count ? "accent" : "plain"} />
        <Metric label="Existing" value={chips[2]!.count} />
        <Metric label="Units" value={units.toLocaleString()} />
        <Metric label="Batch cost" value={formatMoney(cost, currency)} />
        <Metric label="Retail value" value={formatMoney(retail, currency)} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Toggle
          label="Master price policy: update retail price"
          description={
            options.update_master_price
              ? `On commit, ${priceChanges} existing product${priceChanges === 1 ? "" : "s"} take the imported selling price.`
              : "Existing products keep their current master price; the batch still records the imported price."
          }
          checked={options.update_master_price}
          onChange={(checked) => onOptions({ ...options, update_master_price: checked })}
        />
        <label className="block rounded-2xl border border-line p-3">
          <span className="block text-sm font-medium">Batch notes</span>
          <input
            value={notes}
            maxLength={1000}
            onChange={(event) => onNotes(event.target.value)}
            placeholder="Invoice number, delivery reference…"
            className="mt-1.5 h-9 w-full rounded-full border border-line bg-surface px-4 text-sm focus:border-accent focus:bg-white focus:outline-none"
          />
        </label>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter rows">
          {chips.map((chip) => (
            <button
              key={chip.id}
              type="button"
              aria-pressed={filter === chip.id}
              onClick={() => setFilter(chip.id)}
              className={`rounded-full px-3 py-1.5 text-xs font-semibold transition ${
                filter === chip.id ? "bg-charcoal text-white" : "bg-surface text-charcoal/70 hover:text-charcoal"
              }`}
            >
              {chip.label}
              <span
                className={`ml-1.5 tabular-nums ${
                  filter === chip.id ? "text-accent" : chip.id === "ERROR" && chip.count ? "text-accent" : "text-charcoal/40"
                }`}
              >
                {chip.count}
              </span>
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={onRecheck}
          disabled={!dirty || rechecking}
          className={`inline-flex h-9 items-center gap-2 rounded-full px-4 text-xs font-semibold transition ${
            dirty ? "bg-accent text-white hover:bg-accent-hover" : "bg-surface text-charcoal/40"
          } disabled:cursor-not-allowed`}
        >
          <RefreshCw size={13} className={rechecking ? "animate-spin" : ""} aria-hidden="true" />
          {dirty ? "Re-check edited rows" : "All rows checked"}
        </button>
      </div>

      <div className="overflow-auto rounded-2xl border border-line">
        <table className="w-full min-w-[1080px] text-left text-sm">
          <thead>
            <tr className="bg-charcoal text-[11px] font-semibold uppercase tracking-wider text-white/70">
              <th className="w-10 px-3 py-2.5">
                <span className="sr-only">Include</span>
              </th>
              <th className="w-12 px-2 py-2.5">#</th>
              <th className="w-24 px-2 py-2.5">Status</th>
              <th className="px-2 py-2.5">Product</th>
              <th className="w-44 px-2 py-2.5">SKU / Barcode</th>
              <th className="w-20 px-2 py-2.5 text-right">Qty</th>
              <th className="w-28 px-2 py-2.5 text-right">Cost</th>
              <th className="w-28 px-2 py-2.5 text-right">Price</th>
              <th className="w-28 px-3 py-2.5 text-right">Line cost</th>
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 ? (
              <tr>
                <td colSpan={9} className="px-4 py-10 text-center text-sm text-charcoal/50">
                  No rows in this view.
                </td>
              </tr>
            ) : null}
            {visible.map((row) => {
              const off = !row.include;
              const problem = (prefix: string) => row.errors.some((error) => error.startsWith(prefix));
              return (
                <tr
                  key={row.row_number}
                  className={`border-t border-line align-top transition-colors ${
                    off ? "bg-surface/60 opacity-50" : row.status === "ERROR" ? "bg-accent/[0.03]" : "hover:bg-surface/40"
                  }`}
                >
                  <td className="px-3 py-3">
                    <input
                      type="checkbox"
                      aria-label={`Include row ${row.row_number}`}
                      checked={row.include}
                      onChange={(event) => onRow(row.row_number, { include: event.target.checked })}
                      className="h-4 w-4 rounded accent-accent"
                    />
                  </td>
                  <td className="px-2 py-3 font-mono text-xs tabular-nums text-charcoal/50">{row.row_number}</td>
                  <td className="px-2 py-3">
                    <RowBadge status={row.status} />
                  </td>
                  <td className="px-2 py-2">
                    <input
                      aria-label={`Product name, row ${row.row_number}`}
                      value={row.name}
                      onChange={(event) => onRow(row.row_number, { name: event.target.value })}
                      placeholder={row.existing_name ?? "Product name"}
                      className={`${cell} font-medium ${problem("Product name") ? "border-accent/50" : ""}`}
                    />
                    <div className="px-2">
                      {row.status === "EXISTING" && row.existing_name ? (
                        <span className="block truncate text-xs text-charcoal/50">Matches {row.existing_name}</span>
                      ) : null}
                      {row.is_serialized ? (
                        <span className="mt-0.5 inline-flex items-center gap-1 text-xs text-charcoal/60">
                          <Smartphone size={12} aria-hidden="true" /> {row.serials.length} IMEI / serial
                          {row.serials.length === 1 ? "" : "s"}
                        </span>
                      ) : null}
                      <CostDelta existing={row.existing_cost_cents} incoming={row.cost_cents} currency={currency} />
                      {row.include
                        ? row.errors.map((error) => (
                            <span key={error} className="mt-1 flex items-start gap-1 text-xs font-medium text-accent">
                              <AlertTriangle size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                              {error}
                            </span>
                          ))
                        : null}
                      {row.include
                        ? row.warnings.map((warning) => (
                            <span key={warning} className="mt-1 flex items-start gap-1 text-xs text-charcoal/55">
                              <Info size={12} className="mt-0.5 shrink-0" aria-hidden="true" />
                              {warning}
                            </span>
                          ))
                        : null}
                    </div>
                  </td>
                  <td className="px-2 py-2">
                    {row.generated_code && !row.code ? (
                      <span className="flex h-9 items-center gap-1.5 px-2 text-xs font-semibold text-accent">
                        <Sparkles size={13} aria-hidden="true" /> Auto-generated
                      </span>
                    ) : (
                      <input
                        aria-label={`SKU or barcode, row ${row.row_number}`}
                        value={row.code}
                        onChange={(event) => onRow(row.row_number, { code: event.target.value })}
                        className={`${cell} font-mono text-xs ${problem("SKU") ? "border-accent/50" : ""}`}
                      />
                    )}
                  </td>
                  <td className="px-2 py-2">
                    <input
                      aria-label={`Quantity, row ${row.row_number}`}
                      inputMode="numeric"
                      value={row.quantity ?? ""}
                      disabled={row.is_serialized}
                      onChange={(event) => {
                        const digits = event.target.value.replace(/\D/g, "");
                        onRow(row.row_number, { quantity: digits === "" ? null : Number(digits) });
                      }}
                      className={`${cell} text-right tabular-nums disabled:text-charcoal/60 ${problem("Quantity") ? "border-accent/50" : ""}`}
                    />
                  </td>
                  <td className="px-2 py-2">
                    <MoneyCell
                      label={`Purchase cost, row ${row.row_number}`}
                      value={row.cost_cents}
                      invalid={problem("Purchase cost")}
                      onChange={(cents) => onRow(row.row_number, { cost_cents: cents })}
                    />
                  </td>
                  <td className="px-2 py-2">
                    <MoneyCell
                      label={`Selling price, row ${row.row_number}`}
                      value={row.price_cents}
                      invalid={problem("Selling price")}
                      onChange={(cents) => onRow(row.row_number, { price_cents: cents })}
                    />
                    {row.status === "EXISTING" &&
                    row.existing_price_cents !== null &&
                    row.price_cents !== null &&
                    row.existing_price_cents !== row.price_cents ? (
                      <span className="block px-2 text-right text-[11px] tabular-nums text-charcoal/50">
                        Master {formatMoney(row.existing_price_cents, currency)}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-3 py-3 text-right font-semibold tabular-nums">
                    {formatMoney((row.quantity ?? 0) * (row.cost_cents ?? 0), currency)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {errors ? (
        <p className="flex items-start gap-2 rounded-2xl bg-accent/10 px-4 py-3 text-sm text-accent" role="status">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          {errors} included row{errors === 1 ? " has" : "s have"} errors. Fix them in the grid and re-check, or untick
          them to leave them out of this batch.
        </p>
      ) : null}
    </div>
  );
}
