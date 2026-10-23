import { useEffect, useState } from "react";
import { Select } from "@ai-pos/ui";
import { ErrorNote, PrimaryButton, TextField } from "../../components/ui/Field";
import { apiGet } from "../../lib/api";
import { message } from "../customers/api";
import { modelsApi } from "./api";

interface Cell {
  product_id: string;
  sku: string;
  size: string;
  color: string | null;
  received: number;
  sold: number;
  on_hand: number;
  sell_through_bps: number;
  sales_share_bps: number;
  stock_share_bps: number;
}

interface Broken {
  store_name: string;
  size: string;
  color: string | null;
  suggest_from_name: string | null;
  quantity: number;
}

interface Report {
  cells: Cell[];
  broken_runs: Broken[];
}

function tone(bps: number): string {
  if (bps >= 7000) return "bg-emerald-200";
  if (bps >= 4000) return "bg-emerald-100";
  if (bps >= 1500) return "bg-amber-100";
  return "bg-rose-100";
}

/** Sell-through of a model's sizes, and transfers that would refill a broken size run. */
export function SizeCurvePage() {
  const [models, setModels] = useState<{ id: string; name: string }[]>([]);
  const [modelId, setModelId] = useState("");
  const [from, setFrom] = useState(() => new Date(Date.now() - 30 * 86_400_000).toISOString().slice(0, 10));
  const [to, setTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [report, setReport] = useState<Report | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    modelsApi.list().then(setModels).catch(() => setModels([]));
  }, []);

  async function load() {
    if (!modelId) return;
    setError(null);
    try {
      setReport(
        await apiGet<Report>(`/api/v1/reports/size-curve?model_id=${modelId}&from=${from}&to=${to}`),
      );
    } catch (err) {
      setError(message(err, "Could not load the size curve."));
    }
  }

  const sizes = [...new Set(report?.cells.map((cell) => cell.size) ?? [])];
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-semibold text-charcoal">Size curve</h1>
        <p className="mt-1 text-sm text-charcoal/60">Sell-through by size, and sizes that have sold out while the rest of the run is still in stock.</p>
      </div>
      <div className="flex flex-wrap items-end gap-3">
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
        <TextField label="From" type="date" value={from} onChange={(event) => setFrom(event.target.value)} />
        <TextField label="To" type="date" value={to} onChange={(event) => setTo(event.target.value)} />
        <PrimaryButton type="button" onClick={() => void load()} disabled={!modelId}>
          Show
        </PrimaryButton>
      </div>
      <ErrorNote message={error} />
      {report ? (
        <>
          <div className="overflow-x-auto rounded-2xl border border-line">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-charcoal/50">
                  <th className="px-3 py-2">Size</th>
                  <th className="px-3 py-2">Colour</th>
                  <th className="px-3 py-2">Sold</th>
                  <th className="px-3 py-2">On hand</th>
                  <th className="px-3 py-2">Sell-through</th>
                  <th className="px-3 py-2">Sales share</th>
                  <th className="px-3 py-2">Stock share</th>
                </tr>
              </thead>
              <tbody>
                {report.cells.map((cell) => (
                  <tr key={cell.product_id} className={tone(cell.sell_through_bps)}>
                    <td className="px-3 py-2 font-medium">{cell.size}</td>
                    <td className="px-3 py-2">{cell.color ?? "—"}</td>
                    <td className="px-3 py-2">{cell.sold}</td>
                    <td className="px-3 py-2">{cell.on_hand}</td>
                    <td className="px-3 py-2">{(cell.sell_through_bps / 100).toFixed(0)}%</td>
                    <td className="px-3 py-2">{(cell.sales_share_bps / 100).toFixed(0)}%</td>
                    <td className="px-3 py-2">{(cell.stock_share_bps / 100).toFixed(0)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {sizes.length === 0 ? <p className="text-sm text-charcoal/50">Nothing sold or stocked in this range.</p> : null}
          {report.broken_runs.length ? (
            <ul className="space-y-1 text-sm">
              {report.broken_runs.map((run, index) => (
                <li key={`${run.store_name}-${run.size}-${index}`}>
                  {run.store_name} is out of size {run.size}
                  {run.suggest_from_name ? ` — move ${run.quantity} from ${run.suggest_from_name}` : ""}
                </li>
              ))}
            </ul>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
