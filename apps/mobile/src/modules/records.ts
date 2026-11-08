export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export interface CollectedRows {
  rows: Record<string, unknown>[];
  total: number | null;
  summary: Record<string, unknown> | null;
}

const COLLECTION_KEYS = ["rows", "items", "results", "entries", "data", "lines", "transactions"] as const;

export function collectRows(payload: unknown, headerTotal: number | null): CollectedRows {
  if (Array.isArray(payload)) {
    const rows = payload.filter(isRecord);
    return { rows, total: headerTotal ?? rows.length, summary: null };
  }
  if (!isRecord(payload)) return { rows: [], total: headerTotal ?? 0, summary: null };
  for (const key of COLLECTION_KEYS) {
    const value = payload[key];
    if (!Array.isArray(value)) continue;
    const summary: Record<string, unknown> = {};
    for (const [field, fieldValue] of Object.entries(payload)) {
      if (field !== key && !Array.isArray(fieldValue) && !isRecord(fieldValue)) summary[field] = fieldValue;
    }
    const rows = value.filter(isRecord);
    const declared = typeof payload.total === "number" ? payload.total : headerTotal;
    return { rows, total: declared ?? rows.length, summary: Object.keys(summary).length > 0 ? summary : null };
  }
  return { rows: [payload], total: 1, summary: null };
}

const TITLE_FIELDS = ["name", "title", "full_name", "number", "sku", "code", "description", "username", "payee", "label"] as const;
const SUBTITLE_FIELDS = ["sku", "code", "email", "phone", "category", "status", "supplier_name", "store_name", "username"] as const;

export function recordId(row: Record<string, unknown>, index: number): string {
  for (const key of ["id", "product_id", "customer_id", "code", "number"]) {
    const value = row[key];
    if (typeof value === "string" || typeof value === "number") return String(value);
  }
  return `row-${index}`;
}

export function recordTitle(row: Record<string, unknown>): string {
  for (const key of TITLE_FIELDS) {
    const value = row[key];
    if (typeof value === "string" && value.trim() !== "") return value;
  }
  return "Record";
}

export function recordSubtitle(row: Record<string, unknown>, title: string): string {
  const parts: string[] = [];
  for (const key of SUBTITLE_FIELDS) {
    const value = row[key];
    if (typeof value === "string" && value !== title && value.trim() !== "") parts.push(value);
    if (parts.length === 2) break;
  }
  return parts.join(" · ");
}

export function labelize(key: string): string {
  return key
    .replace(/_cents$/, "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function isoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Barcode and text search returns `{ product, match }`. The list shows the product. */
export function unwrapProductHits(payload: unknown): CollectedRows {
  if (!Array.isArray(payload)) return collectRows(payload, null);
  const rows = payload
    .map((hit) => (isRecord(hit) && isRecord(hit.product) ? hit.product : null))
    .filter((row): row is Record<string, unknown> => row !== null);
  return { rows, total: rows.length, summary: null };
}

export function defaultRange(): { from: string; to: string } {
  const to = new Date();
  const from = new Date();
  from.setDate(from.getDate() - 30);
  return { from: isoDate(from), to: isoDate(to) };
}
