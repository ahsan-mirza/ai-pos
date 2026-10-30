import {
  LABEL_LAYOUT_LABELS,
  compareVariantValues,
  formatMoney,
  type LabelLayout,
  type MatrixAxis,
  type MatrixPreview,
  type ProductModel,
  type VariantMatrix,
  variantAttributeLabel,
} from "@ai-pos/shared-types";
import { Grid3x3, Printer } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Select } from "@ai-pos/ui";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { useCurrency } from "../../lib/currency";
import { labelsApi, message, modelsApi } from "./api";
import { VariantGrid } from "./VariantGrid";

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
          <Select
            size="sm"
            className="w-40"
            aria-label="Label layout"
            value={layout}
            onChange={(value) => setLayout(value as LabelLayout)}
            options={(Object.keys(LABEL_LAYOUT_LABELS) as LabelLayout[]).map((value) => ({
              value,
              label: LABEL_LAYOUT_LABELS[value],
            }))}
          />
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

      {matrix ? (
        <div className="mt-4">
          <VariantGrid axes={matrix.axes} cells={matrix.cells} swatches={model.axis_swatches} />
          <p className="mt-2 text-[11px] text-charcoal/50">
            Number = on hand across branches; shading = units sold in 90 days; red = out of stock.
          </p>
        </div>
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

export function MatrixBuilderModal({
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
  const [preview, setPreview] = useState<MatrixPreview | null>(null);
  const [swatches, setSwatches] = useState<Record<string, string>>({});

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

  const payload = {
    axes: parsed.map((axis) => ({ key: axis.key, values: [...axis.values].sort(compareVariantValues) })),
    price_cents: priceCents,
    price_by_value: extraPrices ?? {},
    sku_prefix: prefix.trim() || null,
  };
  const colourAxis = parsed.find((axis) => axis.key === "color" || axis.key === "colour");

  useEffect(() => {
    if (!valid) {
      setPreview(null);
      return;
    }
    const handle = window.setTimeout(() => {
      modelsApi
        .previewMatrix(model.id, payload)
        .then(setPreview)
        .catch(() => setPreview(null));
    }, 250);
    return () => window.clearTimeout(handle);
    // payload is rebuilt from valid, model.id, price, extra, prefix, and axes.
  }, [valid, model.id, price, extra, prefix, axes]);

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      const axisSwatches: Record<string, Record<string, string>> = {};
      if (colourAxis) {
        const colours: Record<string, string> = {};
        for (const value of colourAxis.values) {
          const hex = swatches[`${colourAxis.key}|${value}`];
          if (hex) colours[value] = hex;
        }
        if (Object.keys(colours).length > 0) axisSwatches[colourAxis.key] = colours;
      }
      if (Object.keys(axisSwatches).length > 0) await modelsApi.update(model.id, { axis_swatches: axisSwatches });
      const result = await modelsApi.generateMatrix(model.id, payload);
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
        {colourAxis && colourAxis.values.length > 0 ? (
          <div className="flex flex-wrap gap-3">
            {colourAxis.values.map((value) => (
              <label key={value} className="flex items-center gap-2 text-sm">
                <span>{value}</span>
                <input
                  type="color"
                  aria-label={`${value} swatch`}
                  value={swatches[`${colourAxis.key}|${value}`] ?? "#111111"}
                  onChange={(event) =>
                    setSwatches((current) => ({ ...current, [`${colourAxis.key}|${value}`]: event.target.value }))
                  }
                />
              </label>
            ))}
          </div>
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
          {combinations} combinations, {fresh} new
          {preview ? ` · preview ${preview.creating} to create, ${preview.existing} existing` : ""}
          {preview && preview.inactive > 0 ? `, ${preview.inactive} inactive` : ""}
          {combinations > 400 ? " (the limit is 400)" : ""}. Example SKU{" "}
          <code>{[prefix || model.code || "VAR", ...parsed.map((axis) => (axis.values[0] ?? "X").toUpperCase().slice(0, 5))].join("-")}</code>
          {priceCents > 0 ? ` at ${formatMoney(priceCents, currency)}` : ""}.
        </p>
        {notice ? <p role="status" className="text-sm text-charcoal/70">{notice}</p> : null}
        <ErrorNote message={error ?? (extraPrices === null ? "Write different prices as VALUE=PRICE, separated by commas." : null)} />
      </div>
    </Modal>
  );
}
