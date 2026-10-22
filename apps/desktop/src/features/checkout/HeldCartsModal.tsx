import { formatMoney } from "@ai-pos/shared-types";
import { PauseCircle, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useId, useState } from "react";
import { listHeld, takeHeld, type HeldCart } from "./held";

interface HeldCartsModalProps {
  currency: string;
  /** The current cart has lines, so holding it is offered alongside recalling. */
  canHold: boolean;
  cartEmpty: boolean;
  onHold: (label: string) => Promise<void>;
  onRecall: (cart: HeldCart) => void;
  onClose: () => void;
}

export function HeldCartsModal({ currency, canHold, cartEmpty, onHold, onRecall, onClose }: HeldCartsModalProps) {
  const titleId = useId();
  const [rows, setRows] = useState<HeldCart[]>([]);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    void listHeld()
      .then(setRows)
      .catch((caught: unknown) => setError(String(caught)));
  }, []);
  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onClose]);

  const act = async (work: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await work();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-lg">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <PauseCircle size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              Held sales
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">Park a sale to serve the next customer. Stock is checked again on recall.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} disabled={busy} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        {canHold ? (
          <form
            className="mt-5 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              void act(async () => {
                await onHold(label || `Sale ${new Date().toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`);
                onClose();
              });
            }}
          >
            <input
              autoFocus
              maxLength={60}
              value={label}
              onChange={(event) => setLabel(event.target.value)}
              placeholder="Name it, e.g. lady in blue / table 3"
              className="modal-input flex-1 font-normal"
              aria-label="Name for the held sale"
            />
            <button type="submit" disabled={busy} className="modal-save shrink-0">
              Hold current sale
            </button>
          </form>
        ) : null}

        <ul className="mt-5 max-h-80 space-y-2 overflow-y-auto">
          {rows.length === 0 ? (
            <li className="rounded-2xl border border-dashed border-line dark:border-zinc-800 p-6 text-center text-sm text-charcoal/60 dark:text-zinc-400">No sales on hold.</li>
          ) : null}
          {rows.map((row) => (
            <li key={row.id} className="flex items-center gap-3 rounded-2xl bg-surface dark:bg-zinc-800/60 p-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{row.label}</p>
                <p className="text-xs text-charcoal/60 dark:text-zinc-400 tabular-nums">
                  {row.item_count} item{row.item_count === 1 ? "" : "s"} · {row.cashier_name} ·{" "}
                  {new Date(row.held_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                </p>
              </div>
              <span className="font-semibold tabular-nums">{formatMoney(row.total_cents, currency)}</span>
              <button
                type="button"
                disabled={busy || !cartEmpty}
                title={cartEmpty ? "Recall into the cart" : "Hold or finish the current sale first"}
                onClick={() =>
                  void act(async () => {
                    const cart = await takeHeld(row.id);
                    if (cart) onRecall(cart);
                    onClose();
                  })
                }
                className="rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white disabled:opacity-40"
              >
                Recall
              </button>
              <button
                type="button"
                aria-label={`Discard ${row.label}`}
                disabled={busy}
                onClick={() => {
                  if (!window.confirm(`Discard the held sale "${row.label}"?`)) return;
                  void act(async () => {
                    await takeHeld(row.id);
                    load();
                  });
                }}
                className="flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 dark:text-zinc-400 hover:bg-charcoal/10 dark:hover:bg-white/10 hover:text-charcoal"
              >
                <Trash2 size={15} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        {error ? (
          <p role="alert" className="mt-4 text-sm font-medium text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
