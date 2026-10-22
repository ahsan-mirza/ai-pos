import { compareVariantValues, type MatrixAxis, type ProductUpsert } from "@ai-pos/shared-types";

export interface ModelGroup {
  modelId: string;
  name: string;
  variants: ProductUpsert[];
  fromCents: number;
  toCents: number;
  stock: number;
}

export type GridEntry<H> = { kind: "product"; hit: H } | { kind: "model"; group: ModelGroup; first: H };

export function isVariant(product: ProductUpsert): boolean {
  return Boolean(product.product_model_id) && Object.keys(product.variant_attributes ?? {}).length > 0;
}

export function modelName(product: ProductUpsert): string {
  if (product.model_name) return product.model_name;
  const values = Object.values(product.variant_attributes ?? {});
  let name = product.name;
  for (const value of values) name = name.replace(new RegExp(`\\s*${value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*`, "i"), " ");
  return name.trim() || product.name;
}

/** All of a model's variants from the register catalog (search may have matched only some of them). */
export function modelGroup(modelId: string, catalog: ProductUpsert[]): ModelGroup | null {
  const variants = catalog.filter((product) => product.product_model_id === modelId && isVariant(product));
  if (variants.length === 0) return null;
  const prices = variants.map((product) => product.price_cents);
  return {
    modelId,
    name: modelName(variants[0]!),
    variants,
    fromCents: Math.min(...prices),
    toCents: Math.max(...prices),
    stock: variants.reduce((total, product) => total + Math.max(0, product.stock_quantity), 0),
  };
}

/** Collapses a model's variants in a result list into one card, where the first variant matched. */
export function groupHits<H extends { product: ProductUpsert }>(hits: H[], catalog: ProductUpsert[]): GridEntry<H>[] {
  const entries: GridEntry<H>[] = [];
  const seen = new Set<string>();
  const counts = new Map<string, number>();
  for (const product of catalog) {
    if (isVariant(product)) counts.set(product.product_model_id!, (counts.get(product.product_model_id!) ?? 0) + 1);
  }
  for (const hit of hits) {
    const modelId = hit.product.product_model_id;
    if (!modelId || !isVariant(hit.product) || (counts.get(modelId) ?? 0) < 2) {
      entries.push({ kind: "product", hit });
      continue;
    }
    if (seen.has(modelId)) continue;
    seen.add(modelId);
    const group = modelGroup(modelId, catalog);
    entries.push(group ? { kind: "model", group, first: hit } : { kind: "product", hit });
  }
  return entries;
}

/** The axes a group of variants varies by, values in wear order (S, M, L, XL; 28, 30, 32). */
export function variantAxes(variants: ProductUpsert[]): MatrixAxis[] {
  const values = new Map<string, string[]>();
  for (const product of variants) {
    for (const [key, value] of Object.entries(product.variant_attributes ?? {})) {
      const list = values.get(key) ?? [];
      if (!list.includes(value)) list.push(value);
      values.set(key, list);
    }
  }
  return [...values.entries()].map(([key, list]) => ({ key, values: [...list].sort(compareVariantValues) }));
}

export function findVariant(variants: ProductUpsert[], wanted: Record<string, string>): ProductUpsert | undefined {
  return variants.find((product) =>
    Object.entries(wanted).every(([key, value]) => (product.variant_attributes ?? {})[key] === value),
  );
}
