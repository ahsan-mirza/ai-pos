import { formatMoney, type Category, type Combo, type ComboInput, type Product } from "@ai-pos/shared-types";
import { Plus, Trash2, UtensilsCrossed } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";
import { categoriesApi } from "../inventory/api";

interface OptionDraft {
  product_id: string;
  surcharge: string;
  is_default: boolean;
}

interface SlotDraft {
  key: string;
  name: string;
  min: string;
  max: string;
  options: OptionDraft[];
}

function toCents(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return 0;
  if (!/^\d+(\.\d{1,2})?$/.test(trimmed)) return null;
  return Math.round(Number(trimmed) * 100);
}

const NEW_SLOTS: SlotDraft[] = [
  { key: "main", name: "Main", min: "1", max: "1", options: [] },
  { key: "side", name: "Side", min: "1", max: "1", options: [] },
  { key: "drink", name: "Drink", min: "1", max: "1", options: [] },
];

function slotsOf(combo: Combo | null): SlotDraft[] {
  if (combo === null) return NEW_SLOTS.map((slot) => ({ ...slot, options: [] }));
  return combo.slots.map((slot) => ({
    key: slot.id,
    name: slot.name,
    min: String(slot.min_select),
    max: String(slot.max_select),
    options: slot.options.map((option) => ({
      product_id: option.product_id,
      surcharge: option.surcharge_cents ? (option.surcharge_cents / 100).toFixed(2) : "",
      is_default: option.is_default,
    })),
  }));
}

function MealModal({
  combo,
  products,
  categories,
  mealIds,
  onClose,
  onSaved,
}: {
  combo: Combo | null;
  products: Product[];
  categories: Category[];
  mealIds: Set<string>;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { currency } = useCurrency();
  const [name, setName] = useState(combo?.name ?? "");
  const [price, setPrice] = useState(combo ? (combo.price_cents / 100).toFixed(2) : "");
  const [categoryId, setCategoryId] = useState(combo?.category_id ?? categories[0]?.id ?? "");
  const [slots, setSlots] = useState<SlotDraft[]>(() => slotsOf(combo));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const choices = useMemo(
    () =>
      products
        .filter(
          (product) =>
            !product.is_serialized &&
            !product.sold_by_weight &&
            !product.is_open_price &&
            !product.is_ingredient &&
            !mealIds.has(product.id) &&
            product.id !== combo?.product_id,
        )
        .sort((a, b) => a.category.localeCompare(b.category) || a.name.localeCompare(b.name)),
    [products, mealIds, combo],
  );
  const byId = useMemo(() => new Map(products.map((product) => [product.id, product])), [products]);
  const productOptions = choices.map((product) => ({
    value: product.id,
    label: product.name,
    hint: `${product.category} · ${formatMoney(product.price_cents, currency)}`,
  }));

  const update = (index: number, patch: Partial<SlotDraft>) =>
    setSlots(slots.map((slot, at) => (at === index ? { ...slot, ...patch } : slot)));
  const updateOption = (index: number, optionIndex: number, patch: Partial<OptionDraft>) =>
    update(index, {
      options: slots[index]!.options.map((option, at) => (at === optionIndex ? { ...option, ...patch } : option)),
    });

  async function save() {
    const cents = toCents(price);
    if (name.trim() === "") return setError("Name the meal, e.g. Burger Meal.");
    if (cents === null || price.trim() === "") return setError("Enter the meal price, like 39.00.");
    if (!categoryId) return setError("Choose a category for the meal.");
    if (slots.length === 0) return setError("Add at least one slot.");
    const body: ComboInput = { name: name.trim(), category_id: categoryId, price_cents: cents, slots: [] };
    for (const slot of slots) {
      if (slot.name.trim() === "") return setError("Every slot needs a name, e.g. Side.");
      if (slot.options.length === 0) return setError(`Add at least one item to ${slot.name}.`);
      if (slot.options.some((option) => option.product_id === "")) return setError(`Pick an item for every row in ${slot.name}.`);
      const priced = slot.options.map((option) => ({ ...option, cents: toCents(option.surcharge) }));
      if (priced.some((option) => option.cents === null)) return setError("Enter extra charges like 3.00.");
      body.slots.push({
        name: slot.name.trim(),
        min_select: Number(slot.min) || 0,
        max_select: Math.max(1, Number(slot.max) || 1),
        options: priced.map((option) => ({
          product_id: option.product_id,
          surcharge_cents: option.cents ?? 0,
          is_default: option.is_default,
        })),
      });
    }
    setBusy(true);
    setError(null);
    try {
      if (combo) await apiPut<Combo>(`/api/v1/menu/combos/${combo.product_id}`, body);
      else await apiPost<Combo>("/api/v1/menu/combos", body);
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the meal."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal
      title={combo ? `Edit ${combo.name}` : "New meal"}
      subtitle="A meal sells at one price. The cashier picks each part; every part goes to its own kitchen station and stock."
      onClose={onClose}
      width="lg"
      footer={
        <>
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            {busy ? "Saving…" : "Save meal"}
          </PrimaryButton>
        </>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <TextField label="Meal name" value={name} placeholder="Burger Meal" onChange={(event) => setName(event.target.value)} />
        <TextField label="Price" inputMode="decimal" value={price} placeholder="39.00" onChange={(event) => setPrice(event.target.value)} />
        <SelectField
          label="Category"
          value={categoryId}
          placeholder="Choose a category"
          options={categories.map((category) => ({ value: category.id, label: category.name }))}
          onChange={setCategoryId}
        />
      </div>

      <div className="mt-6 space-y-4">
        {slots.map((slot, index) => (
          <section key={slot.key} className="rounded-2xl border border-line p-4">
            <div className="grid grid-cols-[1fr_110px_110px_auto] items-end gap-2">
              <TextField label="Slot" value={slot.name} placeholder="Side" onChange={(event) => update(index, { name: event.target.value })} />
              <TextField label="Pick at least" type="number" min={0} value={slot.min} onChange={(event) => update(index, { min: event.target.value })} />
              <TextField label="Pick up to" type="number" min={1} value={slot.max} onChange={(event) => update(index, { max: event.target.value })} />
              <button
                type="button"
                aria-label={`Remove ${slot.name || "slot"}`}
                onClick={() => setSlots(slots.filter((_, at) => at !== index))}
                className="mb-2 flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent"
              >
                <Trash2 size={16} aria-hidden="true" />
              </button>
            </div>
            <div className="mt-3 space-y-2">
              {slot.options.map((option, optionIndex) => (
                <div key={`${slot.key}-${optionIndex}`} className="grid grid-cols-[1fr_120px_auto_auto] items-end gap-2">
                  <SelectField
                    label={optionIndex === 0 ? "Item" : ""}
                    value={option.product_id}
                    placeholder="Choose a menu item"
                    options={productOptions}
                    searchable
                    onChange={(value) => updateOption(index, optionIndex, { product_id: value })}
                  />
                  <TextField
                    label={optionIndex === 0 ? "Extra charge" : ""}
                    inputMode="decimal"
                    value={option.surcharge}
                    placeholder="0.00"
                    onChange={(event) => updateOption(index, optionIndex, { surcharge: event.target.value })}
                  />
                  <label className="mb-3 flex items-center gap-1.5 text-xs font-medium text-charcoal/70">
                    <input
                      type="checkbox"
                      checked={option.is_default}
                      onChange={(event) => updateOption(index, optionIndex, { is_default: event.target.checked })}
                      className="h-4 w-4 accent-accent"
                    />
                    Default
                  </label>
                  <button
                    type="button"
                    aria-label={`Remove ${byId.get(option.product_id)?.name ?? "item"}`}
                    onClick={() => update(index, { options: slot.options.filter((_, at) => at !== optionIndex) })}
                    className="mb-2 flex h-9 w-9 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-accent"
                  >
                    <Trash2 size={16} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={() =>
                update(index, {
                  options: [...slot.options, { product_id: "", surcharge: "", is_default: slot.options.length === 0 }],
                })
              }
              className="mt-2 inline-flex items-center gap-1.5 text-sm font-semibold text-accent"
            >
              <Plus size={15} aria-hidden="true" /> Add item
            </button>
          </section>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setSlots([...slots, { key: crypto.randomUUID(), name: "", min: "1", max: "1", options: [] }])}
        className="mt-3 inline-flex items-center gap-1.5 text-sm font-semibold text-accent"
      >
        <Plus size={15} aria-hidden="true" /> Add slot
      </button>
      <ErrorNote message={error} />
    </Modal>
  );
}

/** Meals and combos: one price, parts picked slot by slot (main, side, drink) at the till. */
export function MealsPage() {
  const { currency } = useCurrency();
  const [combos, setCombos] = useState<Combo[] | null>(null);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [editing, setEditing] = useState<Combo | "new" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const confirm = useConfirm();

  const load = useCallback(async () => {
    try {
      const [nextCombos, nextProducts, nextCategories] = await Promise.all([
        apiGet<Combo[]>("/api/v1/menu/combos"),
        apiGet<Product[]>("/api/v1/products?limit=500"),
        categoriesApi.list(),
      ]);
      setCombos(nextCombos);
      setProducts(nextProducts);
      setCategories(nextCategories);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the meals."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const mealIds = useMemo(() => new Set((combos ?? []).map((combo) => combo.product_id)), [combos]);

  async function remove(combo: Combo) {
    const accepted = await confirm({
      title: "Stop selling as a meal",
      message: `Stop selling ${combo.name} as a meal? It stays on the menu as a single item.`,
      confirmLabel: "Stop selling",
      tone: "danger",
    });
    if (!accepted) return;
    try {
      await apiDelete(`/api/v1/menu/combos/${combo.product_id}`);
      void load();
    } catch (caught) {
      setError(message(caught, "Could not remove the meal."));
    }
  }

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent text-white">
              <UtensilsCrossed size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Meals &amp; combos</h2>
              <p className="text-sm text-charcoal/60">
                Sold at one price; each part is cooked at its own station and drawn from its own stock or recipe.
              </p>
            </div>
          </div>
          <PrimaryButton onClick={() => setEditing("new")}>New meal</PrimaryButton>
        </div>
        <ErrorNote message={error} />
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {(combos ?? []).map((combo) => (
            <article key={combo.product_id} className="rounded-2xl border border-line p-4">
              <div className="flex items-baseline justify-between gap-2">
                <button type="button" onClick={() => setEditing(combo)} className="text-left font-semibold hover:text-accent">
                  {combo.name}
                </button>
                <span className="text-sm font-semibold tabular-nums">{formatMoney(combo.price_cents, currency)}</span>
              </div>
              <p className="text-xs text-charcoal/50">{combo.category}</p>
              <ul className="mt-3 space-y-1.5 text-sm">
                {combo.slots.map((slot) => (
                  <li key={slot.id}>
                    <span className="font-medium">{slot.name}: </span>
                    <span className="text-charcoal/70">
                      {slot.options
                        .map((option) =>
                          option.surcharge_cents ? `${option.name} (+${formatMoney(option.surcharge_cents, currency)})` : option.name,
                        )
                        .join(", ")}
                    </span>
                  </li>
                ))}
              </ul>
              <div className="mt-3 flex gap-3 text-xs font-semibold">
                <button type="button" onClick={() => setEditing(combo)} className="text-accent">
                  Edit
                </button>
                <button type="button" onClick={() => void remove(combo)} className="text-charcoal/50 hover:text-accent">
                  Stop as meal
                </button>
              </div>
            </article>
          ))}
        </div>
        {combos !== null && combos.length === 0 ? (
          <p className="py-6 text-sm text-charcoal/60">No meals yet. Create one from items already on your menu.</p>
        ) : null}
      </div>
      {editing ? (
        <MealModal
          combo={editing === "new" ? null : editing}
          products={products}
          categories={categories}
          mealIds={mealIds}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      ) : null}
    </section>
  );
}
