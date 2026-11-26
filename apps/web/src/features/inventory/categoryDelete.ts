import type { Category } from "@ai-pos/shared-types";

export interface AssignedModel {
  id: string;
  name: string;
  brand_name: string;
  sub_category_name: string;
}

export interface CategoryModels {
  model_count: number;
  models: AssignedModel[];
}

/** Other active categories. The category being deleted is not a valid destination. */
export function destinationCategories(categories: readonly Category[], sourceId: string): Category[] {
  return categories.filter((item) => item.id !== sourceId && item.is_active !== false);
}
