import { variantAttributeLabel, type MatrixAxis, type MatrixCell } from "@ai-pos/shared-types";
import { useMemo, useState } from "react";

/** Size x colour (or any two axes) with a third axis as tabs. Cells are existing products, never new rows. */
export function VariantGrid({
  axes,
  cells,
  soldFor,
  swatches,
  selected,
  onOpen,
  onToggle,
}: {
  axes: MatrixAxis[];
  cells: MatrixCell[];
  soldFor?: (cell: MatrixCell) => number;
  swatches?: Record<string, Record<string, string>>;
  selected?: Set<string>;
  onOpen?: (cell: MatrixCell) => void;
  onToggle?: (cell: MatrixCell) => void;
}) {
  const [rowAxis, columnAxis, pageAxis] = axes;
  const [page, setPage] = useState<string | null>(null);
  const pages = pageAxis?.values ?? [];
  const activePage = page && pages.includes(page) ? page : (pages[0] ?? null);
  const maxSold = Math.max(1, ...cells.map((cell) => soldFor?.(cell) ?? cell.sold_90d));
  const cellFor = useMemo(() => {
    const map = new Map<string, MatrixCell>();
    for (const cell of cells) {
      const key = [rowAxis, columnAxis, pageAxis].map((axis) => (axis ? cell.attributes[axis.key] ?? "" : "")).join("|");
      map.set(key, cell);
    }
    return (row: string, column: string) =>
      map.get([row, rowAxis && columnAxis ? column : "", pageAxis ? (activePage ?? "") : ""].join("|"));
  }, [cells, rowAxis, columnAxis, pageAxis, activePage]);

  if (!rowAxis) {
    return <p className="mt-4 text-sm text-charcoal/60">No variant attributes yet. Generate the grid to create them.</p>;
  }

  return (
    <div>
      {pages.length > 1 ? (
        <div className="mb-3 flex flex-wrap gap-1" role="tablist" aria-label={variantAttributeLabel(pageAxis!.key)}>
          {pages.map((value) => (
            <button
              key={value}
              type="button"
              role="tab"
              aria-selected={value === activePage}
              onClick={() => setPage(value)}
              className={`rounded-full px-3 py-1 text-xs font-semibold ${value === activePage ? "bg-charcoal text-white" : "bg-surface text-charcoal/70"}`}
            >
              {value}
            </button>
          ))}
        </div>
      ) : null}
      <div className="overflow-x-auto">
        <table className="text-sm">
          <thead>
            <tr>
              <th className="px-2 pb-2 text-left text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">
                {variantAttributeLabel(rowAxis.key)}
                {columnAxis ? ` \\ ${variantAttributeLabel(columnAxis.key)}` : ""}
              </th>
              {(columnAxis?.values ?? [""]).map((column) => {
                const swatch = columnAxis ? swatches?.[columnAxis.key]?.[column] : undefined;
                return (
                  <th key={column} className="min-w-[92px] px-2 pb-2 text-center text-xs font-semibold">
                    <span className="inline-flex items-center justify-center gap-1">
                      {swatch ? (
                        <span aria-hidden="true" className="inline-block h-2.5 w-2.5 rounded-full border border-black/10" style={{ backgroundColor: swatch }} />
                      ) : null}
                      {column || "Units"}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rowAxis.values.map((row) => (
              <tr key={row}>
                <th scope="row" className="px-2 py-1 text-left text-xs font-semibold">
                  {row}
                </th>
                {(columnAxis?.values ?? [""]).map((column) => {
                  const cell = cellFor(row, column);
                  if (!cell) {
                    return (
                      <td key={column} className="px-1 py-1">
                        <span className="flex h-14 items-center justify-center rounded-xl border border-dashed border-line text-xs text-charcoal/30">
                          —
                        </span>
                      </td>
                    );
                  }
                  const sold = soldFor?.(cell) ?? cell.sold_90d;
                  const heat = sold / maxSold;
                  const out = cell.on_hand <= 0;
                  const picked = selected?.has(cell.product_id) ?? false;
                  return (
                    <td key={column} className="px-1 py-1">
                      <div className="relative">
                        {onToggle ? (
                          <input
                            type="checkbox"
                            aria-label={`Select ${cell.name}`}
                            checked={picked}
                            onChange={() => onToggle(cell)}
                            className="absolute left-1.5 top-1.5 z-10"
                          />
                        ) : null}
                        <button
                          type="button"
                          onClick={() => onOpen?.(cell)}
                          title={`${cell.sku} · ${cell.barcode}`}
                          className={`flex h-14 w-full min-w-[92px] flex-col items-center justify-center rounded-xl border text-center ${
                            cell.is_active === false ? "border-dashed opacity-60" : ""
                          } ${out ? "border-red-200 bg-red-50" : "border-line"} ${picked ? "ring-2 ring-accent" : ""}`}
                          style={out ? undefined : { backgroundColor: `rgb(var(--primary-rgb) / ${0.04 + heat * 0.22})` }}
                        >
                          <span className={`text-base font-semibold tabular-nums ${out ? "text-red-700" : ""}`}>{cell.on_hand}</span>
                          <span className="text-[10px] text-charcoal/60 tabular-nums">{sold} sold</span>
                        </button>
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
