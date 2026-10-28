const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export type FieldErrors = Record<string, string>;

export function requiredError(value: string, label: string): string | undefined {
  if (value.trim() === "") return `Enter ${label}.`;
  return undefined;
}

export function emailError(value: string, required = false): string | undefined {
  const text = value.trim();
  if (text === "") return required ? "Enter an email address." : undefined;
  if (!EMAIL.test(text)) return "Please enter a valid email address.";
  return undefined;
}

/** Collapses whitespace. Store names are display text and are not unique. */
export function normalizeStoreName(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function storeNameError(value: string, required = false): string | undefined {
  const cleaned = normalizeStoreName(value);
  if (cleaned === "") return required ? "Enter a store name." : undefined;
  if (cleaned.length < 2) return "Enter a store name.";
  if (cleaned.length > 120) return "Use 120 characters or fewer.";
  return undefined;
}

/** Amount in major units with at most two decimal places. Empty is an error. */
export function moneyError(value: string, label: string): string | undefined {
  const text = value.trim();
  if (text === "") return `Enter ${label}.`;
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return `Enter ${label} as an amount such as 5000.00.`;
  return undefined;
}

export function lengthError(value: string, label: string, min: number, max: number): string | undefined {
  const text = value.trim();
  if (text.length < min || text.length > max) return `${label} must be ${min}-${max} characters.`;
  return undefined;
}

function sentence(value: string): string {
  const text = value.replace(/^Value error,\s*/i, "").trim();
  if (text === "") return "Check this field.";
  const capitalized = text.charAt(0).toUpperCase() + text.slice(1);
  return /[.!?]$/.test(capitalized) ? capitalized : `${capitalized}.`;
}

/** Pydantic `loc` entries, `details.fields`, or a `field_errors` map become `{ field: message }`. */
export function fieldErrorsFrom(details: unknown, fieldErrors?: unknown): FieldErrors {
  const out: FieldErrors = {};
  if (fieldErrors && typeof fieldErrors === "object" && !Array.isArray(fieldErrors)) {
    for (const [key, value] of Object.entries(fieldErrors)) {
      if (typeof value === "string" && value.trim() !== "") out[key] = sentence(value);
    }
  }
  if (Object.keys(out).length > 0) return out;
  if (details !== null && typeof details === "object" && !Array.isArray(details) && "fields" in details) {
    const fields = details.fields;
    if (fields && typeof fields === "object") {
      for (const [key, value] of Object.entries(fields)) {
        if (typeof value === "string") out[key] = sentence(value);
      }
    }
    return out;
  }
  if (!Array.isArray(details)) return out;
  for (const item of details) {
    if (!item || typeof item !== "object") continue;
    const loc = "loc" in item ? item.loc : undefined;
    const msg = "msg" in item ? item.msg : undefined;
    if (!Array.isArray(loc) || typeof msg !== "string") continue;
    const parts = loc.filter(
      (part): part is string => typeof part === "string" && part !== "body" && part !== "query" && part !== "path",
    );
    const field = parts[parts.length - 1];
    if (field && !out[field]) out[field] = sentence(msg);
  }
  return out;
}
