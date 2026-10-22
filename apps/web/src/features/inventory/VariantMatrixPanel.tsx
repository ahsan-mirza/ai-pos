import {
  LABEL_LAYOUT_LABELS,
  compareVariantValues,
  formatMoney,
  type LabelLayout,
  type MatrixAxis,
  type ProductModel,
  type VariantMatrix,
  variantAttributeLabel,
} from "@ai-pos/shared-types";
import { Grid3x3, Printer } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useCurrency } from "../../lib/currency";
import { labelsApi, message, modelsApi } from "./api";

const AXIS_PRESETS = ["size", "color", "style", "fit", "length", "material"];

function splitValues(text: string): string[] {
  return [...new Set(text.split(/[,\n]/).map((value) => value.trim()).filter(Boolean))];
}

function parsePrices(text: string): Record<string, number> | null {
  const prices: Record<string, number> = {};
  for (const part of text.split(",").map((value) => value.trim()).filter(Boolean)) {
    const match = /^(.+?)\s*=\s*(\d+(?:\.\d{1,2})?)$/.exec(part);
    if (!match) return null;
    prices[match[1]!.trim()] = Math.round(Number(match[2]) * 100);
  }
  return prices;
}

/** Size x colour grid of a model's variants: units on hand and sold in 90 days per cell. */
export function VariantMatrixPanel({
  model,
  canEdit,
  refreshKey,
  onChanged,
}: {
  model: ProductModel;
  canEdit: boolean;
  refreshKey: number;
  onChanged: () => void;
}) {
  const [matrix, setMatrix] = useState<VariantMatrix | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const [layout, setLayout] = useState<LabelLayout>("a4_3x8");
  const [page, setPage] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setMatrix(await modelsApi.matrix(model.id));
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the size grid."));
    }
  }, [model.id]);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  const [rowAxis, columnAxis, pageAxis] = matrix?.axes ?? [];
  const pages = pageAxis?.values ?? [];
  const activePage = page && pages.includes(page) ? page : (pages[0] ?? null);
  const cellFor = useMemo(() => {
    const map = new Map<string, VariantMatrix["cells"][number]>();
    for (const cell of matrix?.cells ?? []) {
      const key = [rowAxis, columnAxis, pageAxis].map((axis) => (axis ? cell.attributes[axis.key] ?? "" : "")).join("|");
      map.set(key, cell);
    }
    return (row: string, column: string) =>
      map.get([row, rowAxis && columnAxis ? column : "", pageAxis ? (activePage ?? "") : ""].join("|"));
  }, [matrix, rowAxis, columnAxis, pageAxis, activePage]);

  const maxSold = Math.max(1, ...(matrix?.cells ?? []).map((cell) => cell.sold_90d));

  return (
    <section className="mb-6 rounded-2xl border border-line p-4" aria-labelledby="matrix-title">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h3 id="matrix-title" className="flex items-center gap-2 text-base font-semibold">
            <Grid3x3 size={16} aria-hidden="true" className="text-accent" /> Size × colour grid
          </h3>
          <p className="text-xs text-charcoal/60">
            {matrix
              ? `${matrix.cells.length} variants · ${matrix.on_hand} on hand · ${matrix.sold_90d} sold in 90 days`
              : "Loading…"}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            aria-label="Label layout"
            value={layout}
            onChange={(event) => setLayout(event.target.value as LabelLayout)}
            className="h-9 rounded-lg border border-line bg-white px-2 text-xs"
          >
            {(Object.keys(LABEL_LAYOUT_LABELS) as LabelLayout[]).map((value) => (
              <option key={value} value={value}>
                {LABEL_LAYOUT_LABELS[value]}
              </option>
            ))}
          </select>
          <GhostButton
            disabled={!matrix?.cells.length}
            onClick={() => void labelsApi.model(model.id, layout).catch((caught: unknown) => setError(message(caught, "Could not print labels.")))}
          >
            <Printer size={15} aria-hidden="true" className="-ml-1 mr-2" /> Labels
          </GhostButton>
          {canEdit ? <PrimaryButton onClick={() => setBuilding(true)}>Build sizes & colours</PrimaryButton> : null}
        </div>
      </div>
      <ErrorNote message={error} />

      {pages.length > 1 ? (
        <div className="mt-3 flex flex-wrap gap-1" role="tablist" aria-label={variantAttributeLabel(pageAxis!.key)}>
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

      {matrix && rowAxis ? (
        <div className="mt-4 overflow-x-auto">
          <table className="text-sm">
            <thead>
              <tr>
                <th className="px-2 pb-2 text-left text-[11px] font-semibold uppercase tracking-wider text-charcoal/50">
                  {variantAttributeLabel(rowAxis.key)}
                  {columnAxis ? ` \\ ${variantAttributeLabel(columnAxis.key)}` : ""}
                </th>
                {(columnAxis?.values ?? [""]).map((column) => (
                  <th key={column} className="min-w-[92px] px-2 pb-2 text-center text-xs font-semibold">
                    {column || "Units"}
                  </th>
                ))}
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
                    const heat = cell.sold_90d / maxSold;
                    const out = cell.on_hand <= 0;
                    return (
                      <td key={column} className="px-1 py-1">
                        <div
                          title={`${cell.sku} · ${cell.barcode}\n${Object.entries(cell.by_store)
                            .map(([code, units]) => `${code}: ${units}`)
                            .join(", ") || "No stock rows"}`}
                          className={`flex h-14 flex-col items-center justify-center rounded-xl border text-center ${
                            out ? "border-red-200 bg-red-50" : "border-line"
                          }`}
                          style={out ? undefined : { backgroundColor: `rgba(253, 55, 6, ${0.04 + heat * 0.22})` }}
                        >
                          <span className={`text-base font-semibold tabular-nums ${out ? "text-red-700" : ""}`}>{cell.on_hand}</span>
                          <span className="text-[10px] text-charcoal/60 tabular-nums">{cell.sold_90d} sold</span>
                        </div>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-[11px] text-charcoal/50">
            Number = on hand across branches; shading = units sold in 90 days; red = out of stock. Hover for SKU and branches.
          </p>
        </div>
      ) : matrix ? (
        <p className="mt-4 text-sm text-charcoal/60">No size or colour attributes yet. Build the grid to create the variants.</p>
      ) : null}

      {building && matrix ? (
        <MatrixBuilderModal
          model={model}
          existing={matrix}
          onClose={() => setBuilding(false)}
          onGenerated={(next) => {
            setMatrix(next);
            setBuilding(false);
            onChanged();
          }}
        />
      ) : null}
    </section>
  );
}

function MatrixBuilderModal({
  model,
  existing,
  onClose,
  onGenerated,
}: {
  model: ProductModel;
  existing: VariantMatrix;
  onClose: () => void;
  onGenerated: (matrix: VariantMatrix) => void;
}) {
  const { currency } = useCurrency();
  const initial: MatrixAxis[] = existing.axes.length
    ? existing.axes
    : [
        { key: "size", values: ["S", "M", "L", "XL"] },
        { key: "color", values: ["Black", "White"] },
      ];
  const [axes, setAxes] = useState(initial.map((axis) => ({ key: axis.key, text: axis.values.join(", ") })));
  const [price, setPrice] = useState(existing.cells[0] ? (existing.cells[0].price_cents / 100).toFixed(2) : "");
  const [extra, setExtra] = useState("");
  const [prefix, setPrefix] = useState(model.code ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const parsed = axes.map((axis) => ({ key: axis.key.trim().toLowerCase(), values: splitValues(axis.text) }));
  const combinations = parsed.reduce((total, axis) => total * Math.max(axis.values.length, 1), 1);
  const existingKeys = new Set(
    existing.cells.map((cell) =>
      Object.entries(cell.attributes)
        .map(([key, value]) => `${key}=${value.toLowerCase()}`)
        .sort()
        .join("|"),
    ),
  );
  const product = (lists: string[][]): string[][] =>
    lists.reduce<string[][]>((rows, values) => rows.flatMap((row) => values.map((value) => [...row, value])), [[]]);
  const fresh = product(parsed.map((axis) => axis.values)).filter(
    (combo) => !existingKeys.has(parsed.map((axis, index) => `${axis.key}=${combo[index]!.toLowerCase()}`).sort().join("|")),
  ).length;
  const priceCents = Math.round(Number(price) * 100);
  const extraPrices = parsePrices(extra);
  const valid =
    parsed.every((axis) => axis.key && axis.values.length > 0) &&
    new Set(parsed.map((axis) => axis.key)).size === parsed.length &&
    Number.isFinite(priceCents) &&
    priceCents >= 0 &&
    price !== "" &&
    extraPrices !== null &&
    combinations <= 400;

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await modelsApi.generateMatrix(model.id, {
        axes: parsed.map((axis) => ({ key: axis.key, values: [...axis.values].sort(compareVariantValues) })),
        price_cents: priceCents,
        price_by_value: extraPrices ?? {},
        sku_prefix: prefix.trim() || null,
      });
      setNotice(`${result.created} variants created, ${result.skipped} already existed.`);
      onGenerated(result);
    } catch (caught) {
      setError(message(caught, "Could not build the variants."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      width="lg"
      title={`Sizes & colours for ${model.name}`}
      subtitle="Every combination becomes a variant with its own SKU and barcode. Existing ones are kept."
      onClose={() => (busy ? undefined : onClose())}
      footer={
        <>
          <GhostButton disabled={busy} onClick={onClose}>
            Cancel
          </GhostButton>
          <PrimaryButton disabled={!valid || busy || fresh === 0} onClick={() => void generate()}>
            {busy ? "Creating…" : fresh === 0 ? "Nothing new to create" : `Create ${fresh} variant${fresh === 1 ? "" : "s"}`}
          </PrimaryButton>
        </>
      }
    >
      <div className="space-y-4">
        {axes.map((axis, index) => (
          <div key={index} className="grid gap-3 sm:grid-cols-[160px_minmax(0,1fr)_auto]">
            <SelectField
              label={`Attribute ${index + 1}`}
              value={AXIS_PRESETS.includes(axis.key) ? axis.key : "custom"}
              options={[
                ...AXIS_PRESETS.map((key) => ({ value: key, label: variantAttributeLabel(key) })),
                { value: "custom", label: "Other…" },
              ]}
              onChange={(value) =>
                setAxes(axes.map((row, at) => (at === index ? { ...row, key: value === "custom" ? "" : value } : row)))
              }
            />
            <TextField
              label="Values (comma separated)"
              value={axis.text}
              onChange={(event) => setAxes(axes.map((row, at) => (at === index ? { ...row, text: event.target.value } : row)))}
            />
            <div className="flex items-end">
              <GhostButton disabled={axes.length === 1} onClick={() => setAxes(axes.filter((_, at) => at !== index))}>
                Remove
              </GhostButton>
            </div>
            {!AXIS_PRESETS.includes(axis.key) ? (
              <TextField
                label="Attribute name"
                value={axis.key}
                onChange={(event) => setAxes(axes.map((row, at) => (at === index ? { ...row, key: event.target.value } : row)))}
              />
            ) : null}
          </div>
        ))}
        {axes.length < 3 ? (
          <GhostButton onClick={() => setAxes([...axes, { key: AXIS_PRESETS.find((key) => !axes.some((axis) => axis.key === key)) ?? "", text: "" }])}>
            Add attribute
          </GhostButton>
        ) : null}
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField label={`Price (${currency})`} inputMode="decimal" value={price} onChange={(event) => setPrice(event.target.value)} />
          <TextField
            label="Different prices"
            hint="e.g. XXL=59.00, Linen=79.00"
            value={extra}
            onChange={(event) => setExtra(event.target.value)}
          />
          <TextField label="SKU prefix" hint="Defaults to the model code" value={prefix} onChange={(event) => setPrefix(event.target.value.toUpperCase())} />
        </div>
        <p className="rounded-2xl bg-surface px-4 py-3 text-sm text-charcoal/70">
          {combinations} combinations, {fresh} new{combinations > 400 ? " (the limit is 400)" : ""}. Example SKU{" "}
          <code>{[prefix || model.code || "VAR", ...parsed.map((axis) => (axis.values[0] ?? "X").toUpperCase().slice(0, 5))].join("-")}</code>
          {priceCents > 0 ? ` at ${formatMoney(priceCents, currency)}` : ""}.
        </p>
        {notice ? <p role="status" className="text-sm text-charcoal/70">{notice}</p> : null}
        <ErrorNote message={error ?? (extraPrices === null ? "Write different prices as VALUE=PRICE, separated by commas." : null)} />
      </div>
    </Modal>
  );
}
