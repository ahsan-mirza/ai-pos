import type { ProductUpsert } from "@ai-pos/shared-types";
import { Package, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { QuantityField, parseSellQuantity } from "./QuantityField";

interface QuantityModalProps {
  product: ProductUpsert;
  onClose: () => void;
  /** Returns false when the cart refused the quantity, so the dialog stays open. */
  onConfirm: (quantity: number) => boolean;
}

/** Asks how many to sell before a tapped product is added to the cart. */
export function QuantityModal({ product, onClose, onConfirm }: QuantityModalProps) {
  const titleId = useId();
  const [quantity, setQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-md">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <Package size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">How many are you selling?</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <form
          className="mt-5 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const count = parseSellQuantity(quantity);
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            if (onConfirm(count)) onClose();
            else setError("That quantity could not be added.");
          }}
        >
          <QuantityField
            id="sell-quantity"
            autoFocus
            value={quantity}
            onChange={(value) => {
              setQuantity(value);
              setError(null);
            }}
          />
          {error ? (
            <p role="alert" className="text-sm font-medium text-red-600 dark:text-red-400">
              {error}
            </p>
          ) : null}
          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save">
              Add to sale
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
