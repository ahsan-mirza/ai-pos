import type { ProductModel } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { Select } from "@ai-pos/ui";
import { PrimaryButton, TextField } from "../../components/ui/Field";
import { modelsApi } from "./api";

interface Cell {
  product_id: string;
  attributes: Record<string, string>;
}

/** Quantities on a size × colour grid, with a pack ratio such as 1-2-3-2-1. */
export function GridQuantityEditor({
  onApply,
}: {
  onApply: (rows: { productId: string; quantity: number }[]) => void;
}) {
  const [models, setModels] = useState<ProductModel[]>([]);
  const [modelId, setModelId] = useState("");
  const [cells, setCells] = useState<Cell[]>([]);
  const [sizes, setSizes] = useState<string[]>([]);
  const [quantities, setQuantities] = useState<Record<string, string>>({});
  const [packs, setPacks] = useState("1");
  const [ratio, setRatio] = useState("1-2-3-2-1");

  useEffect(() => {
    modelsApi.list().then(setModels).catch(() => setModels([]));
  }, []);

  useEffect(() => {
    if (!modelId) return;
    modelsApi
      .matrix(modelId)
      .then((matrix) => {
        const next = matrix.cells.map((cell) => ({ product_id: cell.product_id, attributes: cell.attributes }));
        setCells(next);
        const axis = matrix.axes.find((item) => item.key === "size") ?? matrix.axes[0];
        setSizes(axis?.values ?? []);
        setQuantities({});
      })
      .catch(() => setCells([]));
  }, [modelId]);

  function fill() {
    const weights = ratio.split("-").map((part) => Number(part.trim()));
    const pack = Math.max(1, Number(packs) || 1);
    if (weights.length === 0 || weights.some((weight) => !Number.isInteger(weight) || weight < 0)) return;
    const next: Record<string, string> = {};
    for (const cell of cells) {
      const size = cell.attributes.size ?? Object.values(cell.attributes)[0];
      const index = sizes.indexOf(size ?? "");
      const weight = (index >= 0 && index < weights.length ? weights[index] : weights[weights.length - 1]) ?? 0;
      next[cell.product_id] = String(weight * pack);
    }
    setQuantities(next);
  }

  function apply() {
    const rows = cells
      .map((cell) => ({ productId: cell.product_id, quantity: Number(quantities[cell.product_id] ?? "0") }))
      .filter((row) => Number.isInteger(row.quantity) && row.quantity > 0);
    if (rows.length) onApply(rows);
  }

  if (models.length === 0) return null;
  return (
    <div className="mt-4 rounded-2xl border border-line p-3">
      <p className="text-sm font-semibold">Add by grid</p>
      <div className="mt-2 flex flex-wrap items-end gap-2">
        <label className="text-sm">
          Model
          <Select
            className="mt-1.5"
            aria-label="Model"
            placeholder="Choose a model"
            value={modelId}
            onChange={setModelId}
            options={models.map((model) => ({ value: model.id, label: model.name }))}
          />
        </label>
        <TextField label="Packs" value={packs} onChange={(event) => setPacks(event.target.value)} className="w-20" />
        <TextField label="Size ratio" value={ratio} onChange={(event) => setRatio(event.target.value)} className="w-36" />
        <PrimaryButton type="button" onClick={fill}>
          Fill
        </PrimaryButton>
        <PrimaryButton type="button" onClick={apply} disabled={!cells.length}>
          Add sizes
        </PrimaryButton>
      </div>
    </div>
  );
}
