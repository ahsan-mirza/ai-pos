/** In-store barcode and SKU drafts for the product form. EAN-13 check digits match the API. */

const EAN_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"];
const EAN_G = EAN_L.map((code) => [...code].reverse().map((bit) => (bit === "0" ? "1" : "0")).join(""));
const EAN_R = EAN_L.map((code) => [...code].map((bit) => (bit === "0" ? "1" : "0")).join(""));
const EAN_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"];

const CODE128 = (
  "212222 222122 222221 121223 121322 131222 122213 122312 132212 221213 221312 231212 112232 122132 122231 " +
  "113222 123122 123221 223211 221132 221231 213212 223112 312131 311222 321122 321221 312212 322112 322211 " +
  "212123 212321 232121 111323 131123 131321 112313 132113 132311 211313 231113 231311 112133 112331 132131 " +
  "113123 113321 133121 313121 211331 231131 213113 213311 213131 311123 311321 331121 312113 312311 332111 " +
  "314111 221411 431111 111224 111422 121124 121421 141122 141221 112214 112412 122114 122411 142112 142211 " +
  "241211 221114 413111 241112 134111 111242 121142 121241 114212 124112 124211 411212 421112 421211 212141 " +
  "214121 412121 111143 111341 131141 114113 114311 411113 411311 113141 114131 311141 411131 211412 211214 " +
  "211232 2331112"
).split(" ");

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

export function ean13Modules(code: string): string {
  if (!isEan13(code)) throw new Error("Not an EAN-13.");
  const parity = EAN_PARITY[Number(code[0])] ?? "LLLLLL";
  const left = [...parity]
    .map((side, index) => (side === "L" ? EAN_L : EAN_G)[Number(code[index + 1])])
    .join("");
  const right = [...code.slice(7)].map((digit) => EAN_R[Number(digit)]).join("");
  return `101${left}01010${right}101`;
}

export function code128Modules(text: string): string {
  const values = [104, ...[...text].map((char) => char.charCodeAt(0) - 32)];
  const checksum = (values[0]! + values.slice(1).reduce((sum, value, index) => sum + (index + 1) * value, 0)) % 103;
  let modules = "";
  for (const value of [...values, checksum, 106]) {
    const pattern = CODE128[value] ?? "";
    [...pattern].forEach((width, index) => {
      modules += (index % 2 === 0 ? "1" : "0").repeat(Number(width));
    });
  }
  return modules;
}

export function barcodeModules(code: string): string {
  return isEan13(code) ? ean13Modules(code) : code128Modules(code);
}
