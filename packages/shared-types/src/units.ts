import { UNIT_FACTORS } from "./enums.js";
import { UNIT_LABELS } from "./pricing.js";

/** A pack a product sells in: how many pieces it holds and what to call it (product.unit_options). */
export interface UnitOption {
  code: string;
  name: string;
  short_name: string;
  factor: number;
}

/** GET /api/v1/units row: the built-in packs plus the business's own. */
export interface UnitOfMeasure extends UnitOption {
  id: string | null;
  is_system: boolean;
  is_active: boolean;
  /** Products that currently sell in this unit. */
  products: number;
}

export interface UnitCreate {
  code: string;
  name: string;
  short_name: string;
  factor: number;
}

type WithUnits = { unit_options?: UnitOption[] } | null | undefined;

/** Pieces in one `code` pack for this product: its own unit options first, then the built-in packs. */
export function unitFactor(product: WithUnits, code: string): number {
  return product?.unit_options?.find((option) => option.code === code)?.factor ?? UNIT_FACTORS[code] ?? 1;
}

export function unitLabel(product: WithUnits, code: string, form: "short" | "long" = "long"): string {
  const option = product?.unit_options?.find((item) => item.code === code);
  if (option) return form === "short" ? option.short_name : option.name;
  const builtIn = UNIT_LABELS[code];
  if (builtIn) return builtIn[form];
  return code.replace(/_/g, " ").toLowerCase();
}
