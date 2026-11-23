import {
  activePriceOptions,
  formatMoney,
  priceOptionError,
  type MenuPriceOption,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { Check, Package, X } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";
import { QuantityField, claimSubmit, parseSellQuantity, releaseSubmit, sellLineTotalCents } from "./QuantityField";

interface QuantityModalProps {
  product: ProductUpsert;
  onClose: () => void;
  /** Returns false when the cart refused the quantity, so the dialog stays open. */
  onConfirm: (quantity: number, option: MenuPriceOption | null) => boolean;
  options?: readonly MenuPriceOption[];
  currency?: string;
  initialQuantity?: number;
  initialOptionId?: string | null;
  editing?: boolean;
}

/** Quantity, and a portion when the item has more than one active price, before the line is added. */
export function QuantityModal({
  product,
  onClose,
  onConfirm,
  options = [],
  currency,
  initialQuantity = 1,
  initialOptionId = null,
  editing = false,
}: QuantityModalProps) {
  const titleId = useId();
  const summaryId = useId();
  const active = activePriceOptions(options);
  const needsPortion = active.length >= 2;
  const money = currency ?? product.currency ?? "AED";
  const [selectedId, setSelectedId] = useState<string | null>(initialOptionId);
  const [quantity, setQuantity] = useState(String(initialQuantity));
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);
  const selected = active.find((option) => option.id === selectedId) ?? null;
  const unitCents = needsPortion ? (selected?.price_cents ?? null) : product.price_cents;
  const count = parseSellQuantity(quantity);
  const total = unitCents === null ? null : sellLineTotalCents(unitCents, quantity);
  const blocked = saving || (needsPortion && selected === null) || count === null;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={summaryId}
        className="modal-card flex max-h-[92dvh] w-full min-w-0 max-w-md flex-col overflow-hidden"
      >
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Package size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">
              {needsPortion ? "Choose portion and quantity." : "How many are you selling?"}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-4 flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            if (savingRef.current || saving) return;
            if (needsPortion) {
              const problem = priceOptionError(active, selectedId);
              if (problem || !selected) {
                setError(problem ?? "Choose a portion.");
                return;
              }
            }
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            if (!claimSubmit(savingRef)) return;
            setSaving(true);
            const accepted = onConfirm(count, needsPortion ? selected : null);
            if (accepted) onClose();
            else {
              releaseSubmit(savingRef);
              setSaving(false);
              setError("That quantity could not be added.");
            }
          }}
        >
          <div className="custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto">
            {needsPortion ? (
              <fieldset>
                <legend className="mb-2 text-sm font-semibold">Portion size</legend>
                <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Portion size">
                  {active.map((option) => {
                    const checked = option.id === selectedId;
                    return (
                      <button
                        key={option.id}
                        type="button"
                        role="radio"
                        aria-checked={checked}
                        onClick={() => {
                          setSelectedId(option.id);
                          setError(null);
                        }}
                        className={`choice-control inline-flex items-center gap-2 rounded-2xl px-4 py-2 text-left text-sm font-semibold ${
                          checked ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                        }`}
                      >
                        <span>{option.name}</span>
                        <span className="tabular-nums">{formatMoney(option.price_cents, money)}</span>
                        {checked ? <Check size={16} aria-hidden="true" /> : null}
                      </button>
                    );
                  })}
                </div>
                <p className="mt-2 text-sm">
                  {selected ? `${selected.name} · ${formatMoney(selected.price_cents, money)} each` : "No portion selected"}
                </p>
              </fieldset>
            ) : null}
            <QuantityField
              id="sell-quantity"
              autoFocus
              value={quantity}
              onChange={(value) => {
                setQuantity(value);
                setError(null);
              }}
            />
            <dl id={summaryId} aria-live="polite" className="space-y-1 text-sm">
              <div className="flex justify-between gap-3">
                <dt>Unit price</dt>
                <dd className="tabular-nums">{unitCents === null ? "—" : formatMoney(unitCents, money)}</dd>
              </div>
              <div className="flex justify-between gap-3">
                <dt>Quantity</dt>
                <dd className="tabular-nums">{count ?? "—"}</dd>
              </div>
              <div className="flex justify-between gap-3 text-base font-semibold">
                <dt>Total</dt>
                <dd className="tabular-nums">{total === null ? "—" : formatMoney(total, money)}</dd>
              </div>
            </dl>
            {error ? (
              <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
                {error}
              </p>
            ) : null}
          </div>
          <div className="mt-4 flex shrink-0 justify-end gap-3">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" disabled={blocked} className="modal-save disabled:opacity-60">
              {needsPortion && selected && count !== null && total !== null
                ? `${editing ? "Update" : "Add"} ${count} × ${selected.name} — ${formatMoney(total, money)}`
                : count !== null && total !== null
                  ? `${editing ? "Update" : "Add"} ${count} — ${formatMoney(total, money)}`
                  : editing
                    ? "Update item"
                    : "Add to sale"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
