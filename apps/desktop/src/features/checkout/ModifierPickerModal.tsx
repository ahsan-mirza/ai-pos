import {
  formatMoney,
  modifierDelta,
  modifierSelectionError,
  type ModifierChoice,
  type ModifierGroup,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { Check, X } from "lucide-react";
import { useEffect, useId, useMemo, useState } from "react";
import { QuantityField, parseSellQuantity } from "./QuantityField";

interface ModifierDraft {
  quantity: number;
  choices: ModifierChoice[];
  instruction: string;
}

interface ModifierPickerModalProps {
  product: ProductUpsert;
  groups: ModifierGroup[];
  currency: string;
  /** An existing cart line. Confirm replaces that line instead of adding another. */
  initial?: ModifierDraft | null;
  onClose: () => void;
  onConfirm: (choices: ModifierChoice[], quantity: number, instruction: string) => void;
}

function choiceOf(group: ModifierGroup, optionId: string): ModifierChoice | null {
  const option = group.options.find((item) => item.id === optionId);
  if (!option) return null;
  return { group_id: group.id, option_id: option.id, group: group.name, option: option.name, price_delta_cents: option.price_delta_cents };
}

function startingPicks(groups: ModifierGroup[], initial?: ModifierDraft | null): Record<string, string[]> {
  if (initial) {
    return Object.fromEntries(
      groups.map((group) => [
        group.id,
        initial.choices.filter((choice) => choice.group_id === group.id && group.options.some((option) => option.id === choice.option_id)).map((choice) => choice.option_id),
      ]),
    );
  }
  return Object.fromEntries(groups.map((group) => [group.id, group.options.filter((option) => option.is_default).map((option) => option.id)]));
}

/** Choose a menu item's options. Required groups must be answered before it joins the order. */
export function ModifierPickerModal({ product, groups, currency, initial = null, onClose, onConfirm }: ModifierPickerModalProps) {
  const titleId = useId();
  const [picked, setPicked] = useState<Record<string, string[]>>(() => startingPicks(groups, initial));
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [instruction, setInstruction] = useState(initial?.instruction ?? "");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const choices = useMemo(
    () => groups.flatMap((group) => (picked[group.id] ?? []).flatMap((optionId) => {
      const choice = choiceOf(group, optionId);
      return choice ? [choice] : [];
    })),
    [groups, picked],
  );
  const unit = product.price_cents + modifierDelta(choices);
  const count = parseSellQuantity(quantity);
  const lineTotal = unit * (count ?? 1);
  const extras = modifierDelta(choices);

  function toggle(group: ModifierGroup, optionId: string) {
    setError(null);
    setPicked((current) => {
      const chosen = current[group.id] ?? [];
      if (group.max_select === 1) return { ...current, [group.id]: chosen[0] === optionId && group.min_select === 0 ? [] : [optionId] };
      if (chosen.includes(optionId)) return { ...current, [group.id]: chosen.filter((id) => id !== optionId) };
      if (chosen.length >= group.max_select) return current;
      return { ...current, [group.id]: [...chosen, optionId] };
    });
    const chosen = picked[group.id] ?? [];
    if (group.max_select > 1 && !chosen.includes(optionId) && chosen.length >= group.max_select) {
      setError(`Pick at most ${group.max_select} from ${group.name}.`);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-charcoal/40 sm:items-center sm:p-4" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex h-[100dvh] w-full max-w-3xl flex-col bg-white text-charcoal shadow-2xl sm:h-auto sm:max-h-[92dvh] sm:rounded-3xl dark:bg-zinc-900 dark:text-zinc-100"
      >
        <div className="flex items-start gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="min-w-0 flex-1">
            <h2 id={titleId} className="truncate text-xl font-semibold">
              {product.name}
            </h2>
            <p className="text-sm tabular-nums text-charcoal/60 dark:text-zinc-400">
              {formatMoney(product.price_cents, currency)}
              {extras ? ` · extras ${extras > 0 ? "+" : "−"}${formatMoney(Math.abs(extras), currency)}` : ""}
            </p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl hover:bg-zinc-100 dark:hover:bg-white/10">
            <X size={20} aria-hidden="true" />
          </button>
        </div>

        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            const problem = modifierSelectionError(groups, choices);
            if (problem) {
              setError(problem);
              return;
            }
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            onConfirm(choices, count, instruction.trim().slice(0, 160));
          }}
        >
          <div className="custom-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
            {groups.map((group) => {
              const chosen = picked[group.id] ?? [];
              const single = group.max_select === 1;
              return (
                <fieldset key={group.id}>
                  <legend className="mb-2 flex w-full items-baseline justify-between gap-3 text-base font-semibold">
                    {group.name}
                    <span className="text-xs font-medium text-charcoal/50 dark:text-zinc-400">
                      {group.min_select > 0 ? "Required" : "Optional"}
                      {single ? " · pick one" : ` · up to ${group.max_select}`}
                    </span>
                  </legend>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {group.options.map((option) => {
                      const active = chosen.includes(option.id);
                      return (
                        <button
                          key={option.id}
                          type="button"
                          aria-pressed={active}
                          onClick={() => toggle(group, option.id)}
                          className={`flex min-h-14 items-center justify-between gap-3 rounded-2xl border px-4 py-3 text-left text-base font-semibold active:scale-[0.98] ${
                            active
                              ? "border-primary bg-primary/10 text-zinc-900 dark:text-white"
                              : "border-zinc-200 hover:border-zinc-300 dark:border-zinc-700"
                          }`}
                        >
                          <span className="min-w-0">
                            <span className="block truncate">
                              {option.name}
                              {option.is_default ? <span className="ml-2 text-xs font-medium text-charcoal/50 dark:text-zinc-400">Default</span> : null}
                            </span>
                            {option.price_delta_cents ? (
                              <span className="block text-sm font-medium tabular-nums text-zinc-500 dark:text-white/50">
                                {option.price_delta_cents > 0 ? "+" : "−"}
                                {formatMoney(Math.abs(option.price_delta_cents), currency)}
                              </span>
                            ) : (
                              <span className="block text-sm font-medium text-zinc-400">Included</span>
                            )}
                          </span>
                          {active ? <Check size={20} aria-hidden="true" className="shrink-0 text-primary" /> : null}
                        </button>
                      );
                    })}
                  </div>
                </fieldset>
              );
            })}
            <label className="block">
              <span className="mb-2 block text-base font-semibold">Special instructions</span>
              <textarea
                value={instruction}
                maxLength={160}
                rows={2}
                placeholder="Sauce on the side, no onions, cut into four"
                onChange={(event) => {
                  setInstruction(event.target.value);
                  setError(null);
                }}
                className="min-h-16 w-full resize-none rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-base focus:border-primary focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
              />
            </label>
            <QuantityField
              id="modifier-quantity"
              value={quantity}
              onChange={(value) => {
                setQuantity(value);
                setError(null);
              }}
            />
          </div>
          <div className="border-t border-zinc-200 px-4 py-3 dark:border-zinc-800">
            {error ? (
              <p role="alert" className="mb-2 text-sm font-medium text-red-600 dark:text-red-400">
                {error}
              </p>
            ) : null}
            <button type="submit" className="flex h-14 w-full items-center justify-between rounded-2xl bg-primary px-5 text-base font-semibold text-white">
              <span>{initial ? "Update item" : "Add to order"}</span>
              <span className="tabular-nums">{formatMoney(lineTotal, currency)}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
