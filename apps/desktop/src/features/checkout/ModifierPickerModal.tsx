import {
  formatMoney,
  modifierDelta,
  modifierSelectionError,
  type ModifierChoice,
  type ModifierGroup,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { Check, ChefHat, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { QuantityField, parseSellQuantity } from "./QuantityField";

interface ModifierPickerModalProps {
  product: ProductUpsert;
  groups: ModifierGroup[];
  currency: string;
  onClose: () => void;
  onConfirm: (choices: ModifierChoice[], quantity: number) => void;
}

function choiceOf(group: ModifierGroup, optionId: string): ModifierChoice {
  const option = group.options.find((item) => item.id === optionId)!;
  return { group_id: group.id, option_id: option.id, group: group.name, option: option.name, price_delta_cents: option.price_delta_cents };
}

/** Choose a menu item's options (size, milk, extras); required groups must be answered before it is added. */
export function ModifierPickerModal({ product, groups, currency, onClose, onConfirm }: ModifierPickerModalProps) {
  const titleId = useId();
  const [picked, setPicked] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(groups.map((group) => [group.id, group.options.filter((option) => option.is_default).map((option) => option.id)])),
  );
  const [quantity, setQuantity] = useState("1");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const choices = useMemo(
    () => groups.flatMap((group) => (picked[group.id] ?? []).map((optionId) => choiceOf(group, optionId))),
    [groups, picked],
  );
  const price = product.price_cents + modifierDelta(choices);

  function toggle(group: ModifierGroup, optionId: string) {
    setError(null);
    setPicked((current) => {
      const chosen = current[group.id] ?? [];
      if (group.max_select === 1) return { ...current, [group.id]: chosen[0] === optionId && group.min_select === 0 ? [] : [optionId] };
      if (chosen.includes(optionId)) return { ...current, [group.id]: chosen.filter((id) => id !== optionId) };
      if (chosen.length >= group.max_select) return current;
      return { ...current, [group.id]: [...chosen, optionId] };
    });
  }

  return (
    <div className="modal-backdrop" role="presentation">
      <div role="dialog" aria-modal="true" aria-labelledby={titleId} className="modal-card max-w-lg">
        <div className="flex items-start gap-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-charcoal text-white dark:bg-zinc-100 dark:text-zinc-900">
            <ChefHat size={20} aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm text-charcoal/60 tabular-nums dark:text-zinc-400">{formatMoney(price, currency)}</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="modal-close">
            <X size={18} aria-hidden="true" />
          </button>
        </div>

        <form
          className="mt-4 space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            const problem = modifierSelectionError(groups, choices);
            if (problem) {
              setError(problem);
              return;
            }
            const count = parseSellQuantity(quantity);
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            onConfirm(choices, count);
          }}
        >
          <div className="custom-scrollbar max-h-[55vh] space-y-4 overflow-y-auto pr-1">
            {groups.map((group) => {
              const chosen = picked[group.id] ?? [];
              return (
                <fieldset key={group.id}>
                  <legend className="mb-2 flex w-full items-baseline justify-between text-sm font-semibold">
                    {group.name}
                    <span className="text-[11px] font-medium text-charcoal/50 dark:text-zinc-400">
                      {group.min_select > 0 ? "Required" : "Optional"}
                      {group.max_select > 1 ? ` · up to ${group.max_select}` : ""}
                    </span>
                  </legend>
                  <div className="grid grid-cols-2 gap-2">
                    {group.options.map((option) => {
                      const active = chosen.includes(option.id);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => toggle(group, option.id)}
                          className={`flex min-h-12 items-center justify-between gap-2 rounded-2xl border px-3 py-2 text-left text-sm font-semibold transition-colors ${
                            active
                              ? "border-primary bg-primary/10 text-zinc-900 dark:text-white"
                              : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-700 dark:hover:border-zinc-600"
                          }`}
                        >
                          <span className="min-w-0">
                            <span className="block truncate">{option.name}</span>
                            {option.price_delta_cents ? (
                              <span className="block text-xs font-medium tabular-nums text-zinc-500 dark:text-white/50">
                                {option.price_delta_cents > 0 ? "+" : "−"}
                                {formatMoney(Math.abs(option.price_delta_cents), currency)}
                              </span>
                            ) : null}
                          </span>
                          {active ? <Check size={16} aria-hidden="true" className="shrink-0 text-primary" /> : null}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              );
            })}
          </div>
          <QuantityField
            id="modifier-quantity"
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
              Add {formatMoney(price, currency)}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
