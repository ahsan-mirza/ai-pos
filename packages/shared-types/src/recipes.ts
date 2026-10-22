export interface RecipeLineInput {
  ingredient_id: string;
  /** In the ingredient's stock units: grams for one kept by weight, else pieces (or ml). */
  quantity: number;
}

export interface RecipeInput {
  yield_quantity: number;
  notes?: string | null;
  lines: RecipeLineInput[];
}

export interface RecipeLine extends RecipeLineInput {
  ingredient_name: string;
  sku: string;
  sold_by_weight: boolean;
  /** Per piece, or per kilogram for an ingredient kept by weight; null when no purchase cost is known. */
  unit_cost_cents: number | null;
  cost_cents: number;
  cost_estimated: boolean;
}

export interface Recipe {
  product_id: string;
  product_name: string;
  price_cents: number;
  sold_by_weight: boolean;
  yield_quantity: number;
  notes: string | null;
  lines: RecipeLine[];
  batch_cost_cents: number;
  /** Per portion, or per kilogram for a dish sold by weight. */
  unit_cost_cents: number;
  margin_bps: number | null;
  cost_estimated: boolean;
  updated_at: string | null;
}

export interface ModifierIngredientLine {
  ingredient_id: string;
  /** Per dish sold; negative takes the ingredient out. */
  quantity: number;
  ingredient_name?: string;
  sold_by_weight?: boolean;
}

export interface ModifierRecipe {
  option_id: string;
  lines: ModifierIngredientLine[];
}

export interface UsageVarianceRow {
  ingredient_id: string;
  name: string;
  sku: string;
  sold_by_weight: boolean;
  theoretical: number;
  drawn: number;
  adjustments: number;
  actual: number;
  variance: number;
  variance_cost_cents: number;
}

export interface UsageVarianceReport {
  start: string;
  end: string;
  store_id: string | null;
  rows: UsageVarianceRow[];
}

/** Line cost of an ingredient quantity at its unit cost (per kilogram for weighed ingredients), rounded half up. */
export function ingredientCost(quantity: number, unitCostCents: number | null, soldByWeight: boolean): number {
  if (unitCostCents === null) return 0;
  return soldByWeight ? Math.floor((quantity * unitCostCents + 500) / 1000) : quantity * unitCostCents;
}
