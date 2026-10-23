import {
  comboChoiceOf,
  comboDefaults,
  comboDelta,
  comboSelectionError,
  formatMoney,
  type ComboChoice,
  type ComboSlot,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { Check, UtensilsCrossed, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { QuantityField, parseSellQuantity } from "./QuantityField";

interface ComboBuilderModalProps {
  product: ProductUpsert;
  slots: ComboSlot[];
  currency: string;
  onClose: () => void;
  onConfirm: (components: ComboChoice[], quantity: number) => void;
}

/** Build a meal slot by slot (main, side, drink); defaults are preselected so most meals are one tap. */
export function ComboBuilderModal({ product, slots, currency, onClose, onConfirm }: ComboBuilderModalProps) {
  const titleId = useId();
  const [chosen, setChosen] = useState<ComboChoice[]>(() => comboDefaults(slots));
  const [quantity, setQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const ordered = useMemo(
    () =>
      slots.flatMap((slot) =>
        slot.options.filter((option) => chosen.some((item) => item.slot_id === slot.id && item.product_id === option.product_id))
          .map((option) => comboChoiceOf(slot, option)),
      ),
    [slots, chosen],
  );
  const price = product.price_cents + comboDelta(ordered);

  function toggle(slot: ComboSlot, productId: string) {
    setError(null);
    const option = slot.options.find((item) => item.product_id === productId);
    if (!option) return;
    setChosen((current) => {
      const inSlot = current.filter((item) => item.slot_id === slot.id);
      const others = current.filter((item) => item.slot_id !== slot.id);
      const active = inSlot.some((item) => item.product_id === productId);
      if (slot.max_select === 1) {
        return active && slot.min_select === 0 ? others : [...others, comboChoiceOf(slot, option)];
      }
      if (active) return [...others, ...inSlot.filter((item) => item.product_id !== productId)];
      if (inSlot.length >= slot.max_select) return current;
      return [...current, comboChoiceOf(slot, option)];
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-2xl">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-primary text-white">
            <UtensilsCrossed size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 tabular-nums dark:text-zinc-400">
              Meal {formatMoney(price, currency)}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const problem = comboSelectionError(slots, ordered);
            if (problem) {
              setError(problem);
              return;
            }
            const count = parseSellQuantity(quantity);
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            onConfirm(ordered, count);
          }}
        >
          <div className="custom-scrollbar max-h-[60vh] space-y-4 overflow-y-auto pr-1">
            {slots.map((slot, index) => (
              <fieldset key={slot.id}>
                <legend className="mb-2 flex w-full items-baseline justify-between text-sm font-semibold">
                  <span>
                    <span className="mr-2 inline-flex h-5 w-5 items-center justify-center rounded-full bg-zinc-900 text-[11px] text-white dark:bg-white dark:text-zinc-900">
                      {index + 1}
                    </span>
                    {slot.name}
                  </span>
                  <span className="text-[11px] font-medium text-charcoal/50 dark:text-zinc-400">
                    {slot.min_select > 0 ? "Required" : "Optional"}
                    {slot.max_select > 1 ? ` · up to ${slot.max_select}` : ""}
                  </span>
                </legend>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {slot.options.map((option) => {
                    const active = chosen.some((item) => item.slot_id === slot.id && item.product_id === option.product_id);
                    return (
                      <button
                        key={option.product_id}
                        type="button"
                        aria-pressed={active}
                        onClick={() => toggle(slot, option.product_id)}
                        className={`flex min-h-14 items-center justify-between gap-2 rounded-2xl border px-3 py-2 text-left text-sm font-semibold transition-colors ${
                          active
                            ? "border-primary bg-primary/10 text-zinc-900 dark:text-white"
                            : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600"
                        }`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate">{option.name}</span>
                          <span className="block text-xs font-medium tabular-nums text-zinc-500 dark:text-white/50">
                            {option.surcharge_cents > 0 ? `+${formatMoney(option.surcharge_cents, currency)}` : "Included"}
                          </span>
                        </span>
                        {active ? <Check size={16} aria-hidden="true" className="shrink-0 text-primary" /> : null}
                      </button>
                    );
                  })}
                </div>
              </fieldset>
            ))}
          </div>
          <QuantityField
            id="combo-quantity"
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
          <div className="flex justify-end gap-3 pt-1">
            <button type="button" onClick={onClose} className="modal-cancel">
              Cancel
            </button>
            <button type="submit" className="modal-save">
              Add meal {formatMoney(price, currency)}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
