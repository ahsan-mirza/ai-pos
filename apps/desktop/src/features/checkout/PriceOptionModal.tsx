import {
  formatMoney,
  modifierDelta,
  modifierSelectionError,
  priceOptionError,
  activePriceOptions,
  type MenuPriceOption,
  type ModifierChoice,
  type ModifierGroup,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { Check, X } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { QuantityField, claimSubmit, parseSellQuantity } from "./QuantityField";

interface PriceOptionDraft {
  quantity: number;
  optionId: string;
  choices: ModifierChoice[];
  instruction: string;
  skipRecipe?: boolean;
}

interface PriceOptionModalProps {
  product: ProductUpsert;
  options: MenuPriceOption[];
  groups: ModifierGroup[];
  currency: string;
  hasRecipe?: boolean;
  canSkipRecipe?: boolean;
  /** Restaurant and cafe leave this false. The product setting chooses the ingredient mode. */
  chooseIngredients?: boolean;
  initial?: PriceOptionDraft | null;
  onClose: () => void;
  onConfirm: (
    option: MenuPriceOption | null,
    choices: ModifierChoice[],
    quantity: number,
    instruction: string,
    skipRecipe: boolean,
  ) => void;
}

function choiceOf(group: ModifierGroup, optionId: string): ModifierChoice | null {
  const option = group.options.find((item) => item.id === optionId);
  if (!option) return null;
  return {
    group_id: group.id,
    option_id: option.id,
    group: group.name,
    option: option.name,
    price_delta_cents: option.price_delta_cents,
  };
}

/** Choose exactly one priced serving option, then any modifiers, before the item joins the order. */
export function PriceOptionModal({
  product,
  options,
  groups,
  currency,
  hasRecipe = false,
  canSkipRecipe = false,
  chooseIngredients = true,
  initial = null,
  onClose,
  onConfirm,
}: PriceOptionModalProps) {
  const titleId = useId();
  const active = activePriceOptions(options);
  const [selectedId, setSelectedId] = useState<string | null>(initial?.optionId ?? null);
  const [picked, setPicked] = useState<Record<string, string[]>>(() =>
    Object.fromEntries(
      groups.map((group) => [
        group.id,
        (initial?.choices ?? [])
          .filter((choice) => choice.group_id === group.id && group.options.some((option) => option.id === choice.option_id))
          .map((choice) => choice.option_id),
      ]),
    ),
  );
  const [quantity, setQuantity] = useState(String(initial?.quantity ?? 1));
  const [instruction, setInstruction] = useState(initial?.instruction ?? "");
  const [skipRecipe, setSkipRecipe] = useState(Boolean(initial?.skipRecipe) && canSkipRecipe);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const selected = active.find((option) => option.id === selectedId) ?? null;
  const choices = useMemo(
    () =>
      groups.flatMap((group) =>
        (picked[group.id] ?? []).flatMap((optionId) => {
          const choice = choiceOf(group, optionId);
          return choice ? [choice] : [];
        }),
      ),
    [groups, picked],
  );
  const extras = modifierDelta(choices);
  const needsServing = active.length >= 2;
  const unit = (selected?.price_cents ?? (needsServing ? 0 : product.price_cents)) + extras;
  const count = parseSellQuantity(quantity);

  function toggle(group: ModifierGroup, optionId: string) {
    setError(null);
    setPicked((current) => {
      const chosen = current[group.id] ?? [];
      if (group.max_select === 1) {
        return { ...current, [group.id]: chosen[0] === optionId && group.min_select === 0 ? [] : [optionId] };
      }
      if (chosen.includes(optionId)) return { ...current, [group.id]: chosen.filter((id) => id !== optionId) };
      if (chosen.length >= group.max_select) return current;
      return { ...current, [group.id]: [...chosen, optionId] };
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center overflow-hidden bg-charcoal/40 p-3" role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="flex max-h-[92dvh] max-h-full w-full min-h-0 min-w-0 max-w-xl shrink flex-col overflow-hidden rounded-3xl bg-white text-charcoal shadow-2xl dark:bg-zinc-900 dark:text-zinc-100"
        style={{ maxHeight: "100%" }}
      >
        <div className="flex items-start gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-medium text-charcoal/60 dark:text-zinc-400">
              {needsServing ? "Choose an option" : "Add item"}
            </p>
            <h2 id={titleId} className="truncate text-xl font-semibold">
              {product.name}
            </h2>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl hover:bg-zinc-100 dark:hover:bg-white/10">
            <X size={20} aria-hidden="true" />
          </button>
        </div>
        <form
          className="flex min-h-0 flex-1 flex-col"
          onSubmit={(event) => {
            event.preventDefault();
            if (savingRef.current || saving) return;
            if (needsServing) {
              const problem = priceOptionError(active, selectedId);
              if (problem || !selected) {
                setError(problem ?? "Choose an option.");
                return;
              }
            }
            const modifiers = modifierSelectionError(groups, choices);
            if (modifiers) {
              setError(modifiers);
              return;
            }
            if (count === null) {
              setError("Enter a quantity of at least 1.");
              return;
            }
            if (!claimSubmit(savingRef)) return;
            setSaving(true);
            onConfirm(
              needsServing ? selected : null,
              choices,
              count,
              instruction.trim().slice(0, 160),
              chooseIngredients && hasRecipe && skipRecipe,
            );
          }}
        >
          <div className="custom-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto px-4 py-4">
            {needsServing ? (
            <fieldset>
              <legend className="mb-2 text-base font-semibold">Serving option</legend>
              <div className="grid grid-cols-1 gap-2" role="radiogroup" aria-label="Serving option">
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
                      className={`choice-control flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left text-base font-semibold ${
                        checked ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                      }`}
                    >
                      <span className="min-w-0 truncate">{option.name}</span>
                      <span className="inline-flex shrink-0 items-center gap-2 tabular-nums">
                        {formatMoney(option.price_cents, currency)}
                        {checked ? <Check size={20} aria-hidden="true" className="text-primary" /> : null}
                      </span>
                    </button>
                  );
                })}
              </div>
            </fieldset>
            ) : null}
            {chooseIngredients && hasRecipe ? (
              <fieldset>
                <legend className="mb-2 text-base font-semibold">Ingredient requirement</legend>
                <div className="grid grid-cols-1 gap-2" role="radiogroup" aria-label="Ingredient requirement">
                  <button
                    type="button"
                    role="radio"
                    aria-checked={!skipRecipe}
                    onClick={() => setSkipRecipe(false)}
                    className={`choice-control rounded-2xl px-4 py-3 text-left ${
                      !skipRecipe ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                    }`}
                  >
                    <span className="block font-semibold">Ingredients Required</span>
                    <span className="block text-sm text-charcoal/60 dark:text-zinc-400">Use the configured recipe.</span>
                  </button>
                  <button
                    type="button"
                    role="radio"
                    aria-checked={skipRecipe}
                    aria-disabled={!canSkipRecipe}
                    disabled={!canSkipRecipe}
                    onClick={() => setSkipRecipe(true)}
                    className={`choice-control rounded-2xl px-4 py-3 text-left disabled:cursor-not-allowed disabled:opacity-60 ${
                      skipRecipe ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                    }`}
                  >
                    <span className="block font-semibold">Ingredients Not Required</span>
                    <span className="block text-sm text-charcoal/60 dark:text-zinc-400">
                      {canSkipRecipe
                        ? "Do not require or consume the recipe ingredients for this line."
                        : "Your role cannot skip recipe ingredients. Ingredients Required stays in effect."}
                    </span>
                  </button>
                </div>
              </fieldset>
            ) : null}
            {(needsServing ? selected : true) && groups.length > 0
              ? groups.map((group) => {
                  const chosen = picked[group.id] ?? [];
                  return (
                    <fieldset key={group.id}>
                      <legend className="mb-2 text-base font-semibold">
                        {group.name}
                        <span className="ml-2 text-xs font-medium text-charcoal/50 dark:text-zinc-400">
                          {group.min_select > 0 ? "Required" : "Optional"}
                        </span>
                      </legend>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        {group.options.map((option) => {
                          const pressed = chosen.includes(option.id);
                          return (
                            <button
                              key={option.id}
                              type="button"
                              aria-pressed={pressed}
                              onClick={() => toggle(group, option.id)}
                              className={`choice-control flex items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left ${
                                pressed ? "border-primary bg-primary/10" : "border-zinc-200 dark:border-zinc-700"
                              }`}
                            >
                              <span className="min-w-0 truncate">{option.name}</span>
                              <span className="shrink-0 text-sm tabular-nums">
                                {option.price_delta_cents ? formatMoney(option.price_delta_cents, currency) : "Included"}
                              </span>
                            </button>
                          );
                        })}
                      </div>
                    </fieldset>
                  );
                })
              : null}
            <label className="block">
              <span className="mb-2 block text-base font-semibold">Special instructions</span>
              <textarea
                value={instruction}
                maxLength={160}
                rows={2}
                onChange={(event) => {
                  setInstruction(event.target.value);
                  setError(null);
                }}
                className="min-h-16 w-full resize-none rounded-2xl border border-zinc-200 bg-white px-4 py-3 text-base focus:border-primary focus:outline-none dark:border-zinc-700 dark:bg-zinc-950"
              />
            </label>
            <QuantityField
              id="price-option-quantity"
              value={quantity}
              onChange={(value) => {
                setQuantity(value);
                setError(null);
              }}
            />
          </div>
          <div className="flex shrink-0 flex-col gap-2 border-t border-zinc-200 px-4 py-3 sm:flex-row dark:border-zinc-800">
            {error ? (
              <p role="alert" className="text-sm font-medium text-red-600 sm:flex-1 dark:text-red-400">
                {error}
              </p>
            ) : (
              <p className="text-sm text-charcoal/60 sm:flex-1 dark:text-zinc-400">
                {needsServing && !selected ? "No option selected" : formatMoney(unit, currency)}
              </p>
            )}
            <button type="button" onClick={onClose} className="h-14 rounded-2xl border border-zinc-200 px-5 text-base font-semibold dark:border-zinc-700">
              Cancel
            </button>
            <button type="submit" disabled={saving || (needsServing && selected === null)} className="flex h-14 items-center justify-between gap-4 rounded-2xl bg-primary px-5 text-base font-semibold text-white disabled:opacity-60">
              <span>{initial ? "Update item" : "Add to order"}</span>
              <span className="tabular-nums">
                {needsServing && !selected ? "" : formatMoney(unit * (count ?? 1), currency)}
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
