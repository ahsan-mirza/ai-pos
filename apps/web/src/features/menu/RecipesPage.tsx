import {
  formatMoney,
  formatWeight,
  type ModifierGroup,
  type ModifierRecipe,
  type Product,
  type Recipe,
  type RecipeInput,
} from "@ai-pos/shared-types";
import { BookOpen, Plus, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useConfirm } from "../../components/ui/ConfirmDialog";
import { ErrorNote, GhostButton, PrimaryButton, SelectField, TextField } from "../../components/ui/Field";
import { Modal } from "../../components/ui/Modal";
import { apiDelete, apiGet, apiPost, apiPut } from "../../lib/api";
import { useCurrency } from "../../lib/currency";
import { message } from "../customers/api";

interface LineDraft {
  ingredient_id: string;
  quantity: string;
}

const unitOf = (product: Product | undefined) => (product?.sold_by_weight ? "g" : "pcs");

function amount(product: Product | undefined, quantity: number): string {
  return product?.sold_by_weight ? formatWeight(quantity) : `${quantity} ${quantity === 1 ? "pc" : "pcs"}`;
}

function marginTone(bps: number | null): string {
  if (bps === null) return "bg-surface text-charcoal/60";
  if (bps >= 6500) return "bg-emerald-50 text-emerald-700";
  if (bps >= 4000) return "bg-amber-50 text-amber-700";
  return "bg-red-50 text-red-700";
}

/** Draft a recipe and see the dish cost and margin as the lines change (costed by the API, nothing saved). */
function RecipeEditor({
  dish,
  ingredients,
  existing,
  onClose,
  onSaved,
}: {
  dish: Product;
  ingredients: Product[];
  existing: Recipe | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { currency } = useCurrency();
  const confirm = useConfirm();
  const [yieldQuantity, setYieldQuantity] = useState(String(existing?.yield_quantity ?? (dish.sold_by_weight ? 1000 : 1)));
  const [notes, setNotes] = useState(existing?.notes ?? "");
  const [lines, setLines] = useState<LineDraft[]>(
    existing?.lines.map((line) => ({ ingredient_id: line.ingredient_id, quantity: String(line.quantity) })) ?? [
      { ingredient_id: "", quantity: "" },
    ],
  );
  const [preview, setPreview] = useState<Recipe | null>(existing);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const byId = useMemo(() => new Map(ingredients.map((product) => [product.id, product])), [ingredients]);

  const body = useMemo((): RecipeInput | null => {
    const parsed = lines
      .filter((line) => line.ingredient_id !== "")
      .map((line) => ({ ingredient_id: line.ingredient_id, quantity: Number(line.quantity) }));
    const yieldValue = Number(yieldQuantity);
    if (parsed.length === 0 || parsed.some((line) => !Number.isInteger(line.quantity) || line.quantity < 1)) return null;
    if (!Number.isInteger(yieldValue) || yieldValue < 1) return null;
    return { yield_quantity: yieldValue, notes: notes.trim() || null, lines: parsed };
  }, [lines, yieldQuantity, notes]);

  useEffect(() => {
    if (body === null) return;
    const timer = window.setTimeout(() => {
      apiPost<Recipe>(`/api/v1/recipes/${dish.id}/preview`, body)
        .then((next) => {
          setPreview(next);
          setError(null);
        })
        .catch((caught: unknown) => setError(message(caught, "Could not cost the recipe.")));
    }, 350);
    return () => window.clearTimeout(timer);
  }, [body, dish.id]);

  async function save() {
    if (body === null) return;
    setBusy(true);
    try {
      await apiPut<Recipe>(`/api/v1/recipes/${dish.id}`, body);
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not save the recipe."));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    const accepted = await confirm({
      title: "Remove recipe",
      message: `Remove the recipe for ${dish.name}? Sales will draw the dish's own stock again.`,
      confirmLabel: "Remove",
      tone: "danger",
    });
    if (!accepted) return;
    setBusy(true);
    try {
      await apiDelete(`/api/v1/recipes/${dish.id}`);
      onSaved();
    } catch (caught) {
      setError(message(caught, "Could not remove the recipe."));
      setBusy(false);
    }
  }

  const options = [{ value: "", label: "Choose an ingredient" }, ...ingredients.map((item) => ({ value: item.id, label: item.name }))];
  const costOf = (ingredientId: string) => preview?.lines.find((line) => line.ingredient_id === ingredientId);

  return (
    <Modal
      title={`Recipe: ${dish.name}`}
      subtitle={`Sells at ${formatMoney(dish.price_cents, currency)}${dish.sold_by_weight ? " per kg" : ""}`}
      onClose={onClose}
      width="lg"
      footer={
        <div className="flex w-full items-center gap-2">
          {existing ? (
            <GhostButton onClick={() => void remove()} disabled={busy}>
              <Trash2 size={15} aria-hidden="true" /> Remove recipe
            </GhostButton>
          ) : null}
          <span className="ml-auto" />
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy || body === null} onClick={() => void save()}>
            Save recipe
          </PrimaryButton>
        </div>
      }
    >
      <div className="grid gap-4 md:grid-cols-[1fr_220px]">
        <div className="space-y-3">
          <TextField
            label={dish.sold_by_weight ? "Makes (grams)" : "Makes (portions)"}
            type="number"
            min={1}
            value={yieldQuantity}
            onChange={(event) => setYieldQuantity(event.target.value)}
          />
          <div className="space-y-2">
            {lines.map((line, index) => {
              const ingredient = byId.get(line.ingredient_id);
              const costed = costOf(line.ingredient_id);
              return (
                <div key={index} className="grid grid-cols-[1fr_110px_90px_32px] items-end gap-2">
                  <SelectField
                    label={index === 0 ? "Ingredient" : ""}
                    value={line.ingredient_id}
                    options={options}
                    onChange={(value) => setLines(lines.map((item, at) => (at === index ? { ...item, ingredient_id: value } : item)))}
                  />
                  <TextField
                    label={index === 0 ? "Quantity" : ""}
                    type="number"
                    min={1}
                    value={line.quantity}
                    placeholder={unitOf(ingredient)}
                    onChange={(event) => setLines(lines.map((item, at) => (at === index ? { ...item, quantity: event.target.value } : item)))}
                  />
                  <span className="pb-3 text-right text-sm tabular-nums text-charcoal/70">
                    {costed ? (costed.cost_estimated ? "no cost" : formatMoney(costed.cost_cents, currency)) : "—"}
                  </span>
                  <button
                    type="button"
                    aria-label="Remove line"
                    onClick={() => setLines(lines.filter((_, at) => at !== index))}
                    className="mb-2 flex h-8 w-8 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-red-600"
                  >
                    <Trash2 size={14} aria-hidden="true" />
                  </button>
                </div>
              );
            })}
            <GhostButton onClick={() => setLines([...lines, { ingredient_id: "", quantity: "" }])} disabled={lines.length >= 60}>
              <Plus size={15} aria-hidden="true" /> Ingredient
            </GhostButton>
          </div>
          <TextField label="Notes for the kitchen" value={notes} maxLength={500} onChange={(event) => setNotes(event.target.value)} />
          <ErrorNote message={error} />
        </div>
        <aside className="space-y-3 rounded-2xl bg-surface p-4">
          <div>
            <p className="text-xs text-charcoal/60">Cost {dish.sold_by_weight ? "per kg" : "per portion"}</p>
            <p className="text-2xl font-semibold tabular-nums">{preview ? formatMoney(preview.unit_cost_cents, currency) : "—"}</p>
          </div>
          <div>
            <p className="text-xs text-charcoal/60">Gross margin (before VAT)</p>
            <p className={`mt-1 inline-flex rounded-full px-3 py-1 text-lg font-semibold tabular-nums ${marginTone(preview?.margin_bps ?? null)}`}>
              {preview?.margin_bps != null ? `${(preview.margin_bps / 100).toFixed(1)}%` : "—"}
            </p>
          </div>
          <p className="text-xs text-charcoal/60">
            Whole recipe {preview ? formatMoney(preview.batch_cost_cents, currency) : "—"}. Costs use the latest purchase price of each
            ingredient{preview?.cost_estimated ? "; some ingredients have no purchase cost yet" : ""}.
          </p>
        </aside>
      </div>
    </Modal>
  );
}

function ModifierIngredientsModal({
  option,
  ingredients,
  onClose,
}: {
  option: { id: string; name: string; group: string };
  ingredients: Product[];
  onClose: () => void;
}) {
  const [lines, setLines] = useState<LineDraft[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const byId = useMemo(() => new Map(ingredients.map((product) => [product.id, product])), [ingredients]);

  useEffect(() => {
    apiGet<ModifierRecipe>(`/api/v1/recipes/modifier-options/${option.id}`)
      .then((recipe) => setLines(recipe.lines.map((line) => ({ ingredient_id: line.ingredient_id, quantity: String(line.quantity) }))))
      .catch((caught: unknown) => setError(message(caught, "Could not load the option's ingredients.")));
  }, [option.id]);

  async function save() {
    const parsed = lines
      .filter((line) => line.ingredient_id !== "" && line.quantity.trim() !== "")
      .map((line) => ({ ingredient_id: line.ingredient_id, quantity: Number(line.quantity) }));
    if (parsed.some((line) => !Number.isInteger(line.quantity) || line.quantity === 0)) {
      setError("Quantities are whole numbers; negative takes the ingredient out.");
      return;
    }
    setBusy(true);
    try {
      await apiPut<ModifierRecipe>(`/api/v1/recipes/modifier-options/${option.id}`, { lines: parsed });
      onClose();
    } catch (caught) {
      setError(message(caught, "Could not save."));
      setBusy(false);
    }
  }

  const options = [{ value: "", label: "Choose an ingredient" }, ...ingredients.map((item) => ({ value: item.id, label: item.name }))];
  return (
    <Modal
      title={`${option.group}: ${option.name}`}
      subtitle="What choosing this option adds to (or, negative, takes out of) each dish."
      onClose={onClose}
      footer={
        <div className="flex w-full justify-end gap-2">
          <GhostButton onClick={onClose}>Cancel</GhostButton>
          <PrimaryButton disabled={busy} onClick={() => void save()}>
            Save
          </PrimaryButton>
        </div>
      }
    >
      <div className="space-y-2">
        {lines.map((line, index) => (
          <div key={index} className="grid grid-cols-[1fr_120px_32px] items-end gap-2">
            <SelectField
              label={index === 0 ? "Ingredient" : ""}
              value={line.ingredient_id}
              options={options}
              onChange={(value) => setLines(lines.map((item, at) => (at === index ? { ...item, ingredient_id: value } : item)))}
            />
            <TextField
              label={index === 0 ? "Change" : ""}
              type="number"
              value={line.quantity}
              placeholder={`± ${unitOf(byId.get(line.ingredient_id))}`}
              onChange={(event) => setLines(lines.map((item, at) => (at === index ? { ...item, quantity: event.target.value } : item)))}
            />
            <button
              type="button"
              aria-label="Remove line"
              onClick={() => setLines(lines.filter((_, at) => at !== index))}
              className="mb-2 flex h-8 w-8 items-center justify-center rounded-full text-charcoal/50 hover:bg-surface hover:text-red-600"
            >
              <Trash2 size={14} aria-hidden="true" />
            </button>
          </div>
        ))}
        <GhostButton onClick={() => setLines([...lines, { ingredient_id: "", quantity: "" }])}>
          <Plus size={15} aria-hidden="true" /> Ingredient
        </GhostButton>
        <ErrorNote message={error} />
      </div>
    </Modal>
  );
}

/** Recipes: what each dish is made of, its cost and margin, and what modifier options add or take out. */
export function RecipesPage() {
  const { currency } = useCurrency();
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [groups, setGroups] = useState<ModifierGroup[]>([]);
  const [editing, setEditing] = useState<Product | null>(null);
  const [newDish, setNewDish] = useState("");
  const [option, setOption] = useState<{ id: string; name: string; group: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [nextRecipes, nextProducts, nextGroups] = await Promise.all([
        apiGet<Recipe[]>("/api/v1/recipes"),
        apiGet<Product[]>("/api/v1/products?limit=1000"),
        apiGet<ModifierGroup[]>("/api/v1/menu/modifier-groups").catch(() => [] as ModifierGroup[]),
      ]);
      setRecipes(nextRecipes);
      setProducts(nextProducts);
      setGroups(nextGroups);
      setError(null);
    } catch (caught) {
      setError(message(caught, "Could not load the recipes."));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const withRecipe = new Set(recipes.map((recipe) => recipe.product_id));
  const stocked = products.filter((product) => product.is_ingredient || product.item_type === "RAW_INGREDIENT" || (product.is_stock_tracked && product.item_type === "PRE_PACKAGED"));
  const dishes = products.filter(
    (product) => product.item_type === "MADE_TO_ORDER" && !product.is_service && !withRecipe.has(product.id),
  );
  const byId = new Map(products.map((product) => [product.id, product]));

  return (
    <section className="space-y-4">
      <div className="rounded-card border border-line bg-white p-6">
        <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-2xl bg-charcoal text-white">
              <BookOpen size={20} aria-hidden="true" />
            </span>
            <div>
              <h2 className="text-xl font-semibold">Recipes</h2>
              <p className="text-sm text-charcoal/60">
                A prepared dish draws its ingredients from stock when sold. Raw ingredients and packaged goods stay on the stock overview.
              </p>
            </div>
          </div>
          <div className="flex items-end gap-2">
            <SelectField
              label="New recipe for"
              value={newDish}
              options={[{ value: "", label: "Choose a dish" }, ...dishes.map((dish) => ({ value: dish.id, label: dish.name }))]}
              onChange={setNewDish}
            />
            <PrimaryButton
              disabled={newDish === "" || stocked.length === 0}
              onClick={() => {
                setEditing(byId.get(newDish) ?? null);
                setNewDish("");
              }}
            >
              <Plus size={15} aria-hidden="true" /> Recipe
            </PrimaryButton>
          </div>
        </div>
        <ErrorNote message={error} />
        {stocked.length === 0 ? (
          <p className="mb-4 rounded-2xl bg-amber-50 px-4 py-3 text-sm text-amber-900">
            No ingredients yet. Create raw ingredients or packaged goods (beef patties, buns, bottled drinks) and they show up here.
          </p>
        ) : null}
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-wide text-charcoal/50">
              <th className="py-2">Dish</th>
              <th className="py-2">Ingredients</th>
              <th className="py-2 text-right">Price</th>
              <th className="py-2 text-right">Cost</th>
              <th className="py-2 text-right">Margin</th>
            </tr>
          </thead>
          <tbody>
            {recipes.map((recipe) => (
              <tr key={recipe.product_id} className="cursor-pointer border-b border-line/60 hover:bg-surface" onClick={() => setEditing(byId.get(recipe.product_id) ?? null)}>
                <td className="py-2.5 font-medium">{recipe.product_name}</td>
                <td className="max-w-md truncate py-2.5 text-charcoal/60">
                  {recipe.lines.map((line) => `${line.ingredient_name} ${amount(byId.get(line.ingredient_id), line.quantity)}`).join(", ")}
                </td>
                <td className="py-2.5 text-right tabular-nums">{formatMoney(recipe.price_cents, currency)}</td>
                <td className="py-2.5 text-right tabular-nums">
                  {formatMoney(recipe.unit_cost_cents, currency)}
                  {recipe.cost_estimated ? <span className="text-charcoal/40">*</span> : null}
                </td>
                <td className="py-2.5 text-right">
                  <span className={`rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${marginTone(recipe.margin_bps)}`}>
                    {recipe.margin_bps != null ? `${(recipe.margin_bps / 100).toFixed(1)}%` : "—"}
                  </span>
                </td>
              </tr>
            ))}
            {recipes.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-6 text-center text-charcoal/50">
                  No recipes yet.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
        {recipes.some((recipe) => recipe.cost_estimated) ? (
          <p className="mt-2 text-xs text-charcoal/50">* Some ingredients have no purchase cost yet.</p>
        ) : null}
      </div>

      {groups.length > 0 ? (
        <div className="rounded-card border border-line bg-white p-6">
          <h3 className="font-semibold">Modifier ingredients</h3>
          <p className="mb-3 text-sm text-charcoal/60">Tap an option to say what it adds or takes out, e.g. Extra shot adds 9 g of coffee.</p>
          <div className="space-y-2">
            {groups.map((group) => (
              <div key={group.id} className="flex flex-wrap items-center gap-1.5">
                <span className="w-32 shrink-0 text-sm font-medium">{group.name}</span>
                {group.options
                  .filter((item) => item.is_active)
                  .map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setOption({ id: item.id, name: item.name, group: group.name })}
                      className="h-8 rounded-full border border-line px-3 text-xs font-semibold hover:border-accent"
                    >
                      {item.name}
                    </button>
                  ))}
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {editing ? (
        <RecipeEditor
          dish={editing}
          ingredients={stocked}
          existing={recipes.find((recipe) => recipe.product_id === editing.id) ?? null}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            void load();
          }}
        />
      ) : null}
      {option ? <ModifierIngredientsModal option={option} ingredients={stocked} onClose={() => setOption(null)} /> : null}
    </section>
  );
}
