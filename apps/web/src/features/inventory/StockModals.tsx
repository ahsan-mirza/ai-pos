import { adjustmentReasonLabels, movementLabel, type StockMovement, type StockRow } from "@ai-pos/shared-types";
import { useEffect, useState } from "react";
import { ErrorNote, GhostButton, PrimaryButton, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { inventoryApi, message } from "./api";
import { formatDate } from "./shared";

export function LevelModal({ row, onClose, onSaved }: { row: StockRow; onClose: () => void; onSaved: () => void }) {
  const [minimum, setMinimum] = useState(String(row.min_reorder_level));
  const [maximum, setMaximum] = useState(row.max_stock_level === null ? "" : String(row.max_stock_level));
  const [location, setLocation] = useState(row.aisle_shelf_location ?? "");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const min = Number(minimum);
    const max = maximum.trim() === "" ? null : Number(maximum);
    if (!Number.isInteger(min) || min < 0) return setError("Reorder level must be a whole number.");
    if (max !== null && (!Number.isInteger(max) || max < min)) return setError("Max must be at least the reorder level.");
    if (row.store_id === null) return;
    setBusy(true);
    setError(null);
    try {
      await inventoryApi.updateLevel(row.product_id, row.store_id, {
        min_reorder_level: min,
        ...(max === null ? { clear_max: true } : { max_stock_level: max }),
        aisle_shelf_location: location.trim() || null,
      });
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save stock levels."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      title={`Stock levels · ${row.name}`}
      subtitle={`${row.store_code} · ${row.store_name}`}
      onClose={onClose}
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save levels"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-2">
        <TextField
          label="Min reorder level"
          type="number"
          min={0}
          value={minimum}
          onChange={(event) => setMinimum(event.target.value)}
        />
        <TextField
          label="Max stock level"
          type="number"
          min={0}
          value={maximum}
          hint="Leave empty for no maximum."
          onChange={(event) => setMaximum(event.target.value)}
        />
        <TextField
          label="Aisle / shelf location"
          value={location}
          placeholder="e.g. A1-02"
          onChange={(event) => setLocation(event.target.value)}
        />
      </div>
      <ErrorNote message={error} />
    </Modal>
  );
}

export function MovementsModal({ row, onClose }: { row: StockRow; onClose: () => void }) {
  const [movements, setMovements] = useState<StockMovement[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    inventoryApi
      .movements({ product_id: row.product_id, store_id: row.store_id, limit: 200 })
      .then(setMovements)
      .catch((caught: unknown) => setError(message(caught, "Could not load movements.")));
  }, [row.product_id, row.store_id]);

  return (
    <Modal
      title={`Movements · ${row.name}`}
      subtitle={row.store_code ? `${row.store_code} · ${row.store_name}` : "All branches"}
      onClose={onClose}
      width="lg"
    >
      <ErrorNote message={error} />
      {movements === null ? <p className="text-sm text-charcoal/60">Loading…</p> : null}
      {movements !== null && movements.length === 0 ? (
        <p className="text-sm text-charcoal/60">No stock has moved for this product yet.</p>
      ) : null}
      <ul className="divide-y divide-line">
        {movements?.map((movement) => (
          <li key={movement.id} className="flex items-start justify-between gap-4 py-3 text-sm">
            <span>
              <span className="block font-medium">
                {movementLabel(movement.movement_type)}
                {movement.reason_code ? (
                  <span className="ml-2 rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-charcoal/70">
                    {adjustmentReasonLabels[movement.reason_code]}
                  </span>
                ) : null}
              </span>
              <span className="block text-xs text-charcoal/50">
                {formatDate(movement.created_at)} · {movement.store_code}
                {movement.user_name ? ` · ${movement.user_name}` : ""}
                {movement.note ? ` · ${movement.note}` : ""}
              </span>
            </span>
            <span className="text-right tabular-nums">
              <span className={`block font-semibold ${movement.quantity < 0 ? "text-accent" : ""}`}>
                {movement.quantity > 0 ? `+${movement.quantity}` : movement.quantity}
              </span>
              <span className="block text-xs text-charcoal/50">→ {movement.quantity_after}</span>
            </span>
          </li>
        ))}
      </ul>
    </Modal>
  );
}
