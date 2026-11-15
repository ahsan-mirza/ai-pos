/** Shared form-control widths. The CSS lives in the design tokens. */
export const FIELD_WIDTHS = ["sm", "date", "phone", "md", "lg", "file", "xl", "fluid"] as const;

export type FieldWidth = (typeof FIELD_WIDTHS)[number];

export function fieldClass(width: FieldWidth): string {
  return `field-${width}`;
}

const COMPACT_LABEL = /\b(aed|amount|price|qty|quantity|cost|fee|deposit|percent|percentage)\b/i;

/**
 * Picks a width from the control's purpose.
 * Checkboxes, radios, and anything marked fluid stay with their container.
 */
export function inferFieldWidth(input: {
  type?: string;
  inputMode?: string;
  multiline?: boolean;
  label?: string;
}): FieldWidth {
  if (input.multiline) return "xl";
  const type = (input.type ?? "text").toLowerCase();
  if (type === "hidden" || type === "checkbox" || type === "radio" || type === "range" || type === "color" || type === "button" || type === "submit") {
    return "fluid";
  }
  if (type === "file") return "file";
  if (type === "date" || type === "datetime-local" || type === "time" || type === "month" || type === "week") return "date";
  if (type === "number") return "sm";
  const mode = (input.inputMode ?? "").toLowerCase();
  if (mode === "decimal" || mode === "numeric") return "sm";
  if (input.label && COMPACT_LABEL.test(input.label)) return "sm";
  if (type === "tel") return "phone";
  if (type === "search") return "md";
  if (type === "email" || type === "url" || type === "password" || type === "text") return "lg";
  return "lg";
}
