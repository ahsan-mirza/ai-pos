/** In-store barcode and SKU drafts. Business Pro and the register both use these rules. */

function digits(length: number): string {
  return Array.from({ length }, () => Math.floor(Math.random() * 10)).join("");
}

export function ean13(body: string): string {
  if (!/^\d{12}$/.test(body)) throw new Error("An EAN-13 body is 12 digits.");
  const total = [...body].reduce((sum, digit, position) => sum + Number(digit) * (position % 2 ? 3 : 1), 0);
  return body + String((10 - (total % 10)) % 10);
}

export function isEan13(code: string): boolean {
  return /^\d{13}$/.test(code) && ean13(code.slice(0, 12)) === code;
}

/** In-store EAN-13. Prefix 200–299 is the GS1 range for store-assigned codes. */
export function randomEan13(prefix: string): string {
  const head = prefix.replace(/\D/g, "").slice(0, 11) || "200";
  return ean13((head + digits(12)).slice(0, 12));
}

export function randomCode128(prefix: string): string {
  const head = prefix.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, 8);
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const tail = Array.from({ length: 8 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join("");
  return `${head}${tail}`.slice(0, 20);
}

function chunk(value: string, max: number): string {
  return value.toUpperCase().replace(/[^A-Z0-9]/g, "").slice(0, max);
}

/** Prefix plus the name and variant values, e.g. HP-ELI-256G-8GB-SIL. */
export function skuFromParts(prefix: string, name: string, attributes: Record<string, string>): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((word, index) => chunk(word, index === 0 ? 3 : 5));
  const variants = Object.values(attributes)
    .map((value) => chunk(value, 6))
    .filter(Boolean);
  return [chunk(prefix, 8), ...words, ...variants].filter(Boolean).join("-").slice(0, 64).replace(/-$/, "");
}

export function barcodeError(code: string, taken: boolean): string | null {
  const value = code.trim();
  if (value === "") return "Barcode is required.";
  if (taken) return "Barcode must be unique and 8-13 digits.";
  if (/^\d+$/.test(value)) {
    if (value.length < 8 || value.length > 13) return "Barcode must be unique and 8-13 digits.";
    if (value.length === 13 && !isEan13(value)) return "Barcode must be a valid EAN-13.";
    return null;
  }
  if ([...value].some((char) => char.charCodeAt(0) < 32 || char.charCodeAt(0) > 126) || value.length > 48) {
    return "Code 128 barcodes use printable characters, up to 48.";
  }
  return null;
}

/** Sanitises a code as it is typed, keeping a trailing dash so the user can keep typing. */
export function cleanCode(value: string, maxLength = 32): string {
  return value
    .toUpperCase()
    .replace(/[^A-Z0-9\s-]/g, "")
    .replace(/\s+/g, "-")
    .replace(/-+/g, "-")
    .replace(/^-/, "")
    .slice(0, maxLength);
}
