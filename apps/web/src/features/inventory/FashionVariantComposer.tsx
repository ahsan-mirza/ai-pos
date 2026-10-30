import {
  applyBulkToDrafts,
  mergeVariantDrafts,
  variantCombinations,
  variantDraftKey,
  blankDraft,
  draftSku,
  type VariantDraft,
  type VariantDraftField,
} from "@ai-pos/shared-types";
import { Grid3x3 } from "lucide-react";
import { useMemo, useState } from "react";
import { GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";

const cell =
  "h-9 w-full min-w-[88px] rounded-lg border border-slate-200 bg-white px-2 text-xs text-charcoal focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:bg-slate-50 disabled:text-charcoal/50";

export function FashionVariantComposer({
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
  const [bulkPrice, setBulkPrice] = useState("");
  const [bulkCost, setBulkCost] = useState("");
  const [bulkOpening, setBulkOpening] = useState("");
  const [bulkReorder, setBulkReorder] = useState("");
  const [manual, setManual] = useState<Record<string, string>>({});
  const usable = axes.filter((axis) => axis.values.length > 0);
  const combinations = useMemo(() => variantCombinations(usable), [usable]);
  const axisOrder = usable.map((axis) => axis.key);
  const defaults = {
    price: defaultPrice,
    opening: defaultOpening || "0",
    reorder: defaultReorder || "0",
    skuPrefix: skuPrefix || productName,
    axisOrder,
  };
  const included = rows.filter((row) => row.included).length;
  const existing = rows.filter((row) => row.existingId).length;

  const generate = (includeAll = false) => {
    onChange(mergeVariantDrafts(rows, combinations, defaults, { includeAll }));
  };

  const patch = (key: string, field: VariantDraftField, value: string | boolean) => {
    onChange(
      rows.map((row) =>
        row.key === key ? { ...row, [field]: value, locked: { ...row.locked, [field]: true } } : row,
      ),
    );
  };

  const applyBulk = (field: "price" | "cost" | "opening" | "reorder", value: string) => {
    if (value.trim() === "") return;
    onChange(applyBulkToDrafts(rows, field, value.trim()));
  };

  const addManual = () => {
    if (usable.some((axis) => (manual[axis.key] ?? "") === "")) return;
    const attributes = Object.fromEntries(usable.map((axis) => [axis.key, manual[axis.key]!]));
    const key = variantDraftKey(attributes);
    const found = rows.find((row) => row.key === key);
    if (found) {
      onChange(rows.map((row) => (row.key === key ? { ...row, included: true } : row)));
      return;
    }
    const taken = new Set(rows.map((row) => row.sku.toLowerCase()));
    let sku = draftSku(defaults.skuPrefix, attributes, axisOrder);
    let suffix = 2;
    while (taken.has(sku.toLowerCase())) {
      sku = `${draftSku(defaults.skuPrefix, attributes, axisOrder)}-${suffix}`;
      suffix += 1;
    }
    onChange([...rows, { ...blankDraft(attributes, { ...defaults, sku }, true), manual: true }]);
    setManual({});
  };

  return (
    <section className="mt-4 rounded-2xl border border-line p-4" aria-labelledby="variant-matrix-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 id="variant-matrix-title" className="flex items-center gap-2 text-sm font-semibold">
            <Grid3x3 size={16} aria-hidden="true" className="text-accent" /> Size and color variants
          </h3>
          <p className="mt-1 text-xs text-charcoal/60">
            {combinations.length === 0
              ? "Select at least one size or color, then generate the combinations you actually sell."
              : `${combinations.length} possible combination${combinations.length === 1 ? "" : "s"}. ${included} included${
                  existing ? ` · ${existing} already in the catalog` : ""
                }. Excluded combinations are not created.`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <GhostButton disabled={combinations.length === 0 || rows.length === 0} onClick={() => generate(true)}>
            Include all
          </GhostButton>
          <PrimaryButton disabled={combinations.length === 0} onClick={() => generate(false)}>
            {rows.length === 0 ? "Generate variants" : "Add new combinations"}
          </PrimaryButton>
        </div>
      </div>

      {rows.length > 0 ? (
        <>
          <div className="mt-4 grid gap-3 sm:grid-cols-4">
            <TextField label="Bulk price" inputMode="decimal" value={bulkPrice} onChange={(event) => setBulkPrice(event.target.value)} />
            <TextField label="Bulk cost" inputMode="decimal" value={bulkCost} onChange={(event) => setBulkCost(event.target.value)} />
            <TextField label="Bulk opening stock" inputMode="numeric" value={bulkOpening} onChange={(event) => setBulkOpening(event.target.value)} />
            <TextField label="Bulk reorder level" inputMode="numeric" value={bulkReorder} onChange={(event) => setBulkReorder(event.target.value)} />
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <GhostButton onClick={() => applyBulk("price", bulkPrice)}>Apply price where not edited</GhostButton>
            <GhostButton onClick={() => applyBulk("cost", bulkCost)}>Apply cost where not edited</GhostButton>
            <GhostButton onClick={() => applyBulk("opening", bulkOpening)}>Apply stock where not edited</GhostButton>
            <GhostButton onClick={() => applyBulk("reorder", bulkReorder)}>Apply reorder where not edited</GhostButton>
          </div>
          <p className="mt-2 text-[11px] text-charcoal/50">
            Bulk fill skips a cell you already edited, and it does not change stock or cost already recorded on a variant.
          </p>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[880px] text-left text-xs">
              <thead>
                <tr className="text-[11px] uppercase tracking-wider text-charcoal/50">
                  <th className="py-2 pr-2">Sell</th>
                  {usable.map((axis) => (
                    <th key={axis.key} className="py-2 pr-2">
                      {axis.label}
                    </th>
                  ))}
                  <th className="py-2 pr-2">SKU</th>
                  <th className="py-2 pr-2">Barcode</th>
                  <th className="py-2 pr-2">Cost</th>
                  <th className="py-2 pr-2">Price</th>
                  <th className="py-2 pr-2">Opening stock</th>
                  <th className="py-2 pr-2">Reorder</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.key} className={`border-t border-line ${row.included ? "" : "opacity-50"}`}>
                    <td className="py-2 pr-2">
                      <input
                        type="checkbox"
                        aria-label={`Sell ${Object.values(row.attributes).join(" ")}`}
                        checked={row.included}
                        onChange={(event) => {
                          const included = event.target.checked;
                          onChange(
                            rows.map((item) =>
                              item.key === row.key ? { ...item, included, active: included, locked: { ...item.locked, active: true } } : item,
                            ),
                          );
                        }}
                      />
                    </td>
                    {usable.map((axis) => (
                      <td key={axis.key} className="py-2 pr-2 font-medium">
                        {row.attributes[axis.key] ?? "—"}
                      </td>
                    ))}
                    <td className="py-2 pr-2">
                      <input className={cell} value={row.sku} aria-label={`SKU ${row.key}`} onChange={(event) => patch(row.key, "sku", event.target.value.toUpperCase())} />
                    </td>
                    <td className="py-2 pr-2">
                      <input className={cell} value={row.barcode} aria-label={`Barcode ${row.key}`} onChange={(event) => patch(row.key, "barcode", event.target.value)} />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        className={cell}
                        inputMode="decimal"
                        disabled={row.existingId !== null}
                        value={row.cost}
                        aria-label={`Cost ${row.key}`}
                        onChange={(event) => patch(row.key, "cost", event.target.value)}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <input className={cell} inputMode="decimal" value={row.price} aria-label={`Price ${row.key}`} onChange={(event) => patch(row.key, "price", event.target.value)} />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        className={cell}
                        inputMode="numeric"
                        disabled={row.existingId !== null}
                        value={row.opening}
                        aria-label={row.existingId ? `On hand ${row.key}` : `Opening stock ${row.key}`}
                        onChange={(event) => patch(row.key, "opening", event.target.value)}
                      />
                    </td>
                    <td className="py-2 pr-2">
                      <input
                        className={cell}
                        inputMode="numeric"
                        disabled={row.existingId !== null}
                        value={row.reorder}
                        aria-label={`Reorder ${row.key}`}
                        onChange={(event) => patch(row.key, "reorder", event.target.value)}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {usable.length > 0 ? (
            <div className="mt-4 flex flex-wrap items-end gap-3">
              {usable.map((axis) => (
                <SelectField
                  key={axis.key}
                  label={axis.label}
                  value={manual[axis.key] ?? ""}
                  options={[{ value: "", label: `Choose ${axis.label.toLowerCase()}` }, ...axis.values.map((value) => ({ value, label: value }))]}
                  onChange={(value) => setManual((current) => ({ ...current, [axis.key]: value }))}
                />
              ))}
              <GhostButton disabled={usable.some((axis) => (manual[axis.key] ?? "") === "")} onClick={addManual}>
                Add combination
              </GhostButton>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
