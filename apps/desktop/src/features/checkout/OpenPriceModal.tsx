import { formatMoney, type ProductUpsert } from "@ai-pos/shared-types";
import { PencilLine, X } from "lucide-react";
import { useEffect, useId, useState } from "react";
import { QuantityField, parseSellQuantity } from "./QuantityField";

interface OpenPriceModalProps {
  product: ProductUpsert;
  currency: string;
  /** False when the cashier lacks pos:open_price; the server rejects such lines, so the modal says so up front. */
  allowed: boolean;
  onClose: () => void;
  onConfirm: (description: string, unitPriceCents: number, quantity: number) => void;
}

/** Open-price items (labour, misc accessories) are priced at the till; the description prints on the invoice. */
export function OpenPriceModal({ product, currency, allowed, onClose, onConfirm }: OpenPriceModalProps) {
  const titleId = useId();
  const [description, setDescription] = useState("");
  const [quantity, setQuantity] = useState("1");
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);
  const cents = Math.round(Number.parseFloat(amount.replace(/,/g, "") || "0") * 100);
  const count = parseSellQuantity(quantity) ?? 0;
  const lineCents = count > 0 && cents > 0 ? cents * count : 0;

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
            <PencilLine size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 dark:text-zinc-400">Priced at the till. Enter how many and the price.</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {allowed ? (
          <form
            className="mt-5 space-y-4"
            onSubmit={(event) => {
              event.preventDefault();
              const count = parseSellQuantity(quantity);
              if (count === null) {
                setError("Enter a quantity of at least 1.");
                return;
              }
              if (!Number.isFinite(cents) || cents <= 0) {
                setError("Enter the price.");
                return;
              }
              onConfirm(description.trim(), cents, count);
            }}
          >
            <label className="block text-sm font-medium" htmlFor="open-price">
              Price ({currency})
              <input
                id="open-price"
                autoFocus
                inputMode="decimal"
                autoComplete="off"
                value={amount}
                onChange={(event) => {
                  setAmount(event.target.value.replace(/[^\d.,]/g, ""));
                  setError(null);
                }}
                placeholder="0.00"
                className="modal-input mt-1.5 text-lg font-semibold tabular-nums"
              />
            </label>
            <QuantityField
              id="open-quantity"
              value={quantity}
              onChange={(value) => {
                setQuantity(value);
                setError(null);
              }}
            />
            <label className="block text-sm font-medium" htmlFor="open-description">
              Description (optional)
              <textarea
                id="open-description"
                rows={3}
                maxLength={120}
                value={description}
                onChange={(event) => {
                  setDescription(event.target.value);
                  setError(null);
                }}
                placeholder={product.name.toLowerCase().includes("labour") ? "Screen replacement, iPhone 13" : "USB-C car charger, 30W"}
                className="modal-input mt-1.5 min-h-24 resize-y font-normal"
              />
            </label>
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
                Add {lineCents > 0 ? formatMoney(lineCents, currency) : ""}
              </button>
            </div>
          </form>
        ) : (
          <div className="mt-5 space-y-4">
            <p className="rounded-2xl bg-surface dark:bg-zinc-800/60 px-4 py-3 text-sm text-charcoal/70 dark:text-zinc-300">
              Your role cannot ring up open-price items. Ask a manager to sign in, or to grant the "Open-price items"
              permission to your role.
            </p>
            <div className="flex justify-end">
              <button type="button" onClick={onClose} className="modal-save">
                OK
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
