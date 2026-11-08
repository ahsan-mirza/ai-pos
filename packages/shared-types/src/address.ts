/** Physical store address. The store code is a separate, shorter login value. */
export const ADDRESS_MAX_LENGTH = 255;

/** Removes leading and trailing whitespace. Internal spaces and punctuation stay. */
export function normalizeAddress(value: string): string {
  return value.trim();
}

/**
 * Empty is allowed only when the address is optional.
 * Whitespace-only text and values over 255 characters are rejected.
 * The returned text is never rewritten into a slug.
 */
export function addressError(value: string, required = false): string | undefined {
  if (typeof value !== "string") return "Enter the store address.";
  if (value !== "" && value.trim() === "") return "Enter the store address.";
  const text = value.trim();
  if (text === "") return required ? "Enter the store address." : undefined;
  if (text.length > ADDRESS_MAX_LENGTH) return "Use 255 characters or fewer.";
  return undefined;
}
