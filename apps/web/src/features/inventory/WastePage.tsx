import { useEffect, useState } from "react";
import { ErrorNote, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { apiGet, apiPost } from "../../lib/api";
import { errorMessage } from "../users/api";

interface WasteSource {
  batch_item_id: string;
  product_name: string;
  batch_number: string;
  expiry_date: string | null;
  quantity_remaining: number;
  sold_by_weight: boolean;
}

interface WasteRow {
  id: string;
  created_at: string;
  product_name: string;
  quantity: number;
  reason_code: string;
  note: string | null;
}

const REASONS = [
  { value: "SPOILAGE", label: "Spoilage" },
  { value: "DAMAGED_OR_EXPIRED", label: "Damaged or expired" },
  { value: "QUALITY_REJECTION", label: "Quality rejection" },
  { value: "OTHER", label: "Other" },
];

/** Record produce that left the shelf before it was sold. The same form id cannot deduct twice. */
export function WastePage() {
  const [sources, setSources] = useState<WasteSource[]>([]);
  const [history, setHistory] = useState<WasteRow[]>([]);
  const [batchItemId, setBatchItemId] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [reason, setReason] = useState("SPOILAGE");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    void apiGet<WasteSource[]>("/api/v1/inventory/waste/sources").then(setSources).catch((caught: unknown) => setError(errorMessage(caught)));
    void apiGet<WasteRow[]>("/api/v1/inventory/waste").then(setHistory).catch(() => undefined);
  };

  useEffect(load, []);

  const selected = sources.find((row) => row.batch_item_id === batchItemId);

  const submit = async () => {
    if (!batchItemId) return;
    setBusy(true);
    setError(null);
    try {
      await apiPost("/api/v1/inventory/waste", {
        adjustment_id: crypto.randomUUID(),
        batch_item_id: batchItemId,
        quantity: Number(quantity),
        reason_code: reason,
        note: note.trim() || null,
      });
      setNote("");
      load();
    } catch (caught) {
      setError(errorMessage(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page-enter mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold">Produce waste</h1>
      <p className="mt-1 text-sm text-charcoal/60">Take spoiled or rejected stock off a batch, including batches that have not expired yet.</p>
      <div className="mt-6 space-y-3 rounded-2xl border border-line p-4">
        <SelectField
          label="Batch"
          value={batchItemId}
          options={sources.map((row) => ({
            value: row.batch_item_id,
            label: `${row.product_name} · ${row.batch_number} · ${row.quantity_remaining}${row.sold_by_weight ? " g" : ""} left`,
          }))}
          onChange={setBatchItemId}
        />
        <TextField
          label={selected?.sold_by_weight ? "Quantity (grams)" : "Quantity"}
          type="number"
          min={1}
          value={quantity}
          onChange={(event) => setQuantity(event.target.value)}
        />
        <SelectField label="Reason" value={reason} options={REASONS} onChange={setReason} />
        <TextField label="Note" value={note} onChange={(event) => setNote(event.target.value)} />
        {error ? <ErrorNote>{error}</ErrorNote> : null}
        <PrimaryButton disabled={busy || batchItemId === ""} onClick={() => void submit()}>
          {busy ? "Saving…" : "Record waste"}
        </PrimaryButton>
      </div>
      <ul className="mt-6 divide-y divide-line rounded-2xl border border-line">
        {history.map((row) => (
          <li key={row.id} className="flex items-center justify-between px-4 py-3 text-sm">
            <span>
              {row.product_name}
              <span className="ml-2 text-charcoal/50">{row.reason_code}</span>
            </span>
            <span className="tabular-nums">{row.quantity}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
