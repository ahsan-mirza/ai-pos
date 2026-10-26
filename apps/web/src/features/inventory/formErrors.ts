import { fieldErrorsFrom, focusFirstInvalid } from "@ai-pos/ui";
import { useEffect, useState } from "react";
import { ApiRequestError } from "../../lib/api";

export type FieldErrors = Record<string, string>;

const FIELD_ALIASES: Record<string, string> = {
  credit_limit_cents: "limit",
  price_cents: "price",
  category_id: "category",
  sub_category_id: "sub",
  brand_id: "brand",
  product_model_id: "model",
  plu_code: "plu",
  opening_store_id: "store",
  release_year: "year",
};

const CODE = /^[A-Z0-9][A-Z0-9-]{0,31}$/;

function sentence(value: string): string {
  const text = value.replace(/^Value error,\s*/i, "").trim();
  if (text === "") return "Check this field.";
  const capitalized = text.charAt(0).toUpperCase() + text.slice(1);
  return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`;
}

function assign(target: FieldErrors, field: string, message: string): void {
  const name = FIELD_ALIASES[field] ?? field;
  if (!target[name]) target[name] = sentence(message);
}

/** Pydantic `loc`/`msg` entries, `field_errors`, and catalog `details.fields` become `{ field: message }`. */
export function fieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiRequestError)) return {};
  const parsed = fieldErrorsFrom(error.details, error.fieldErrors);
  const out: FieldErrors = {};
  for (const [key, value] of Object.entries(parsed)) assign(out, key, value);
  return out;
}

export function codeError(value: string): string {
  const normalized = value.trim().toUpperCase().replace(/-$/, "");
  if (normalized === "") return "";
  if (!CODE.test(normalized)) return "Code must be 1-32 characters: letters, digits, and dashes.";
  return "";
}

export { focusFirstInvalid };

/** Call the returned function in the same update as the field errors so focus lands after they render. */
export function useInvalidFocus(root: { current: HTMLElement | null }): () => void {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    if (tick === 0) return;
    focusFirstInvalid(root.current);
  }, [tick, root]);
  return () => setTick((value) => value + 1);
}
