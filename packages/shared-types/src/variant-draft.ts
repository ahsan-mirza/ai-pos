/** Client-side size/colour drafts. The API creates one product per included row and skips rows that already exist. */

export type VariantDraftField = "sku" | "barcode" | "price" | "cost" | "opening" | "reorder" | "active";

export interface VariantDraft {
  key: string;
  attributes: Record<string, string>;
  included: boolean;
  existingId: string | null;
  sku: string;
  barcode: string;
  price: string;
  cost: string;
  opening: string;
  reorder: string;
  active: boolean;
  /** Individual edits, and values loaded from an existing variant. Bulk fill skips these. */
  locked: Partial<Record<VariantDraftField, boolean>>;
  manual?: boolean;
}

export interface VariantCellSource {
  attributes: Record<string, string>;
  product_id: string;
  sku: string;
  barcode: string;
  price_cents: number;
  cost_cents?: number | null;
  on_hand: number;
  is_active?: boolean;
}

export function variantDraftKey(attributes: Record<string, string>): string {
  return Object.entries(attributes)
    .map(([key, value]) => [key.trim().toLowerCase(), value.trim().toLowerCase()] as const)
    .filter(([key, value]) => key !== "" && value !== "")
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([key, value]) => `${key}=${value}`)
    .join("|");
}

/** Cartesian product of the axes that have at least one value. Empty axes are ignored. */
export function variantCombinations(axes: { key: string; values: string[] }[]): Record<string, string>[] {
  const usable = axes
    .map((axis) => ({ key: axis.key, values: axis.values.map((value) => value.trim()).filter(Boolean) }))
    .filter((axis) => axis.values.length > 0);
  if (usable.length === 0) return [];
  return usable.reduce<Record<string, string>[]>(
    (rows, axis) => rows.flatMap((row) => axis.values.map((value) => ({ ...row, [axis.key]: value }))),
    [{}],
  );
}

export function abbreviateVariantValue(value: string): string {
  const words = value.toUpperCase().match(/[A-Z0-9]+/g) ?? [];
  if (words.length === 0) return "X";
  if (words.length === 1) return words[0]!.slice(0, 5);
  return words
    .slice(0, 2)
    .map((word) => word.slice(0, 3))
    .join("");
}

export function draftSku(prefix: string, attributes: Record<string, string>, axisOrder: string[]): string {
  const head = prefix.toUpperCase().replace(/[^A-Z0-9-]/g, "").slice(0, 16) || "VAR";
  const parts = axisOrder
    .map((key) => attributes[key])
    .filter((value): value is string => Boolean(value))
    .map(abbreviateVariantValue);
  return [head, ...parts].filter(Boolean).join("-").slice(0, 64).replace(/-$/, "");
}

function uniqueSku(stem: string, taken: Set<string>): string {
  const base = stem.slice(0, 64).replace(/-$/, "") || "VAR";
  let sku = base;
  let suffix = 2;
  while (taken.has(sku.toLowerCase())) {
    const tail = `-${suffix}`;
    sku = `${base.slice(0, 64 - tail.length)}${tail}`;
    suffix += 1;
  }
  taken.add(sku.toLowerCase());
  return sku;
}

export function blankDraft(
  attributes: Record<string, string>,
  defaults: { price: string; opening: string; reorder: string; sku: string },
  manual = false,
): VariantDraft {
  return {
    key: variantDraftKey(attributes),
    attributes,
    included: true,
    existingId: null,
    sku: defaults.sku,
    barcode: "",
    price: defaults.price,
    cost: "",
    opening: defaults.opening,
    reorder: defaults.reorder,
    active: true,
    locked: {},
    manual,
  };
}

/**
 * Adds combinations that are not in `previous`. Rows already listed keep their edits and their excluded state,
 * so regenerating does not duplicate or resurrect a combination the user turned off. A saved variant whose size
 * or color was removed stays in the list, unchecked, so it can be marked inactive instead of deleted.
 */
export function mergeVariantDrafts(
  previous: VariantDraft[],
  combinations: Record<string, string>[],
  defaults: { price: string; opening: string; reorder: string; skuPrefix: string; axisOrder: string[] },
  options?: { includeAll?: boolean },
): VariantDraft[] {
  const previousByKey = new Map(previous.map((row) => [row.key, row]));
  const taken = new Set(previous.map((row) => row.sku.trim().toLowerCase()).filter(Boolean));
  const next: VariantDraft[] = [];
  const seen = new Set<string>();
  for (const attributes of combinations) {
    const key = variantDraftKey(attributes);
    if (key === "" || seen.has(key)) continue;
    seen.add(key);
    const existing = previousByKey.get(key);
    if (existing) {
      next.push(options?.includeAll ? { ...existing, included: true } : existing);
      continue;
    }
    const sku = uniqueSku(draftSku(defaults.skuPrefix, attributes, defaults.axisOrder), taken);
    next.push(blankDraft(attributes, { price: defaults.price, opening: defaults.opening, reorder: defaults.reorder, sku }));
  }
  for (const row of previous) {
    if (seen.has(row.key)) continue;
    if (row.manual) {
      next.push(options?.includeAll ? { ...row, included: true } : row);
      continue;
    }
    // A size or color that was removed from the selection. Keep a saved variant so it can be turned off
    // instead of being deleted, and drop a combination that was never saved.
    if (row.existingId) next.push({ ...row, included: false });
  }
  return next;
}

/** Fills a price or stock column. Locked cells and existing stock or cost stay as they are. */
export function applyBulkToDrafts(
  rows: VariantDraft[],
  field: "price" | "cost" | "opening" | "reorder",
  value: string,
): VariantDraft[] {
  return rows.map((row) => {
    if (!row.included || row.locked[field]) return row;
    if ((field === "opening" || field === "cost" || field === "reorder") && row.existingId) return row;
    return { ...row, [field]: value };
  });
}

export function draftsFromCells(cells: VariantCellSource[]): VariantDraft[] {
  return cells.map((cell) => ({
    key: variantDraftKey(cell.attributes),
    attributes: { ...cell.attributes },
    included: cell.is_active !== false,
    existingId: cell.product_id,
    sku: cell.sku,
    barcode: cell.barcode,
    price: (cell.price_cents / 100).toFixed(2),
    cost: cell.cost_cents != null ? (cell.cost_cents / 100).toFixed(2) : "",
    opening: String(cell.on_hand),
    reorder: "",
    active: cell.is_active !== false,
    locked: { sku: true, barcode: true, price: true, cost: true, opening: true, reorder: true, active: true },
  }));
}
