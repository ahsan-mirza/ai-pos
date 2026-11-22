import {
  applyBulkToDrafts,
  blankDraft,
  draftSku,
  mergeVariantDrafts,
  variantCombinations,
  variantDraftKey,
  type VariantDraft,
  type VariantDraftField,
} from "@ai-pos/shared-types";
import { Select } from "@ai-pos/ui";
import { useMemo, useState } from "react";

const cell = "h-9 w-full min-w-[5.5rem] rounded-lg border border-zinc-200 bg-white px-2 text-xs";

/** Size and colour combinations. One included row becomes one product through the existing matrix API. */
export function FashionMatrix({
  axes,
  productName,
  skuPrefix,
  defaultPrice,
  defaultOpening,
  defaultReorder,
  rows,
  onChange,
}: {
  axes: { key: string; label: string; values: string[] }[];
  productName: string;
  skuPrefix: string;
  defaultPrice: string;
  defaultOpening: string;
  defaultReorder: string;
  rows: VariantDraft[];
  onChange: (rows: VariantDraft[]) => void;
}) {
  const [bulk, setBulk] = useState({ price: "", cost: "", opening: "", reorder: "" });
  const [manual, setManual] = useState<Record<string, string>>({});
  const usable = axes.filter((axis) => axis.values.length > 0);
  const combinations = useMemo(() => variantCombinations(usable), [usable]);
  const defaults = { price: defaultPrice, opening: defaultOpening || "0", reorder: defaultReorder || "0", skuPrefix: skuPrefix || productName, axisOrder: usable.map((axis) => axis.key) };
  const included = rows.filter((row) => row.included).length;

  const patch = (key: string, field: VariantDraftField, value: string | boolean) => {
    onChange(rows.map((row) => (row.key === key ? { ...row, [field]: value, locked: { ...row.locked, [field]: true } } : row)));
  };

  return (
    <section className="mt-4 rounded-2xl border border-zinc-200 p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Size and color variants</h3>
          <p className="mt-1 text-xs text-zinc-500">
            {combinations.length === 0
              ? "Select at least one size or color, then generate the combinations you actually sell."
              : `${combinations.length} possible combinations. ${included} included. Excluded combinations are not created.`}
          </p>
        </div>
        <div className="flex gap-2">
          <button type="button" disabled={combinations.length === 0 || rows.length === 0} className="h-9 rounded-full px-3 text-xs font-semibold ring-1 ring-zinc-300 disabled:opacity-40" onClick={() => onChange(mergeVariantDrafts(rows, combinations, defaults, { includeAll: true }))}>
            Include all
          </button>
          <button type="button" disabled={combinations.length === 0} className="h-9 rounded-full bg-orange-500 px-3 text-xs font-semibold text-white disabled:opacity-40" onClick={() => onChange(mergeVariantDrafts(rows, combinations, defaults, { includeAll: false }))}>
            {rows.length === 0 ? "Generate variants" : "Add new combinations"}
          </button>
        </div>
      </div>
      {rows.length > 0 ? (
        <div className="mt-3 overflow-x-auto">
          <div className="mb-2 flex flex-wrap gap-2">
            {(["price", "cost", "opening", "reorder"] as const).map((field) => (
              <label key={field} className="text-xs">
                Bulk {field}
                <input className={`${cell} mt-1`} value={bulk[field]} onChange={(event) => setBulk({ ...bulk, [field]: event.target.value })} />
              </label>
            ))}
            <button
              type="button"
              className="h-9 self-end rounded-full px-3 text-xs font-semibold ring-1 ring-zinc-300"
              onClick={() => {
                let next = rows;
                if (bulk.price.trim() !== "") next = applyBulkToDrafts(next, "price", bulk.price.trim());
                if (bulk.cost.trim() !== "") next = applyBulkToDrafts(next, "cost", bulk.cost.trim());
                if (bulk.opening.trim() !== "") next = applyBulkToDrafts(next, "opening", bulk.opening.trim());
                if (bulk.reorder.trim() !== "") next = applyBulkToDrafts(next, "reorder", bulk.reorder.trim());
                onChange(next);
              }}
            >
              Apply bulk where not edited
            </button>
          </div>
          <table className="w-full min-w-[47.5rem] text-left text-xs">
            <thead>
              <tr className="uppercase tracking-wider text-zinc-500">
                <th className="py-2">Sell</th>
                {usable.map((axis) => <th key={axis.key} className="py-2">{axis.label}</th>)}
                <th>SKU</th><th>Barcode</th><th>Cost</th><th>Price</th><th>Opening</th><th>Reorder</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="border-t border-zinc-100">
                  <td><input type="checkbox" checked={row.included} onChange={(event) => onChange(rows.map((item) => item.key === row.key ? { ...item, included: event.target.checked, active: event.target.checked } : item))} /></td>
                  {usable.map((axis) => <td key={axis.key} className="py-2 font-medium">{row.attributes[axis.key] ?? "—"}</td>)}
                  <td><input className={cell} value={row.sku} onChange={(event) => patch(row.key, "sku", event.target.value.toUpperCase())} /></td>
                  <td><input className={cell} value={row.barcode} onChange={(event) => patch(row.key, "barcode", event.target.value)} /></td>
                  <td><input className={cell} disabled={row.existingId !== null} value={row.cost} onChange={(event) => patch(row.key, "cost", event.target.value)} /></td>
                  <td><input className={cell} value={row.price} onChange={(event) => patch(row.key, "price", event.target.value)} /></td>
                  <td><input className={cell} disabled={row.existingId !== null} value={row.opening} onChange={(event) => patch(row.key, "opening", event.target.value)} /></td>
                  <td><input className={cell} disabled={row.existingId !== null} value={row.reorder} onChange={(event) => patch(row.key, "reorder", event.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            {usable.map((axis) => (
              <label key={axis.key} className="text-xs">
                {axis.label}
                <Select
                  value={manual[axis.key] ?? ""}
                  options={[{ value: "", label: `Choose ${axis.label}` }, ...axis.values.map((value) => ({ value, label: value }))]}
                  onChange={(value) => setManual((current) => ({ ...current, [axis.key]: value }))}
                />
              </label>
            ))}
            <button
              type="button"
              className="h-9 rounded-full px-3 text-xs font-semibold ring-1 ring-zinc-300 disabled:opacity-40"
              disabled={usable.some((axis) => (manual[axis.key] ?? "") === "")}
              onClick={() => {
                const attributes = Object.fromEntries(usable.map((axis) => [axis.key, manual[axis.key]!]));
                const key = variantDraftKey(attributes);
                if (rows.some((row) => row.key === key)) {
                  onChange(rows.map((row) => (row.key === key ? { ...row, included: true } : row)));
                  return;
                }
                onChange([...rows, { ...blankDraft(attributes, { ...defaults, sku: draftSku(defaults.skuPrefix, attributes, defaults.axisOrder) }, true), manual: true }]);
                setManual({});
              }}
            >
              Add combination
            </button>
          </div>
        </div>
      ) : null}
    </section>
  );
}
