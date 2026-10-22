import type { Product, ProductSearchHit, ProductUpsert } from "./product.js";

type SearchableProduct = ProductUpsert | Product;

const MAX_TOKENS = 6;
const IDENTIFIER = /^[A-Za-z0-9-]{4,64}$/;

export const SEARCH_DEBOUNCE_MS = 150;

export function noMatchesMessage(query: string): string {
  return `No products found matching "${query}". Try searching by name, model, barcode, SKU, or IMEI.`;
}

export function searchTokens(query: string): string[] {
  return query.trim().toLowerCase().split(/\s+/).filter(Boolean).slice(0, MAX_TOKENS);
}

function compact(value: string): string {
  return value.toLowerCase().replace(/[\s\-_./]/g, "");
}

/** True when the query could be an IMEI or serial number; those resolve only on the server, by exact hash. */
export function looksLikeIdentifier(query: string): boolean {
  const value = query.trim();
  return IDENTIFIER.test(value) && /\d/.test(value) && value.length >= 8;
}

function haystack(product: SearchableProduct): { text: string[]; compacted: string[] } {
  const fields = [product.name, product.model_number, product.barcode, product.sku, product.category, product.brand]
    .filter((value): value is string => typeof value === "string" && value !== "")
    .map((value) => value.toLowerCase());
  const compacted = [product.model_number, product.sku, product.barcode]
    .filter((value): value is string => typeof value === "string" && value !== "")
    .map(compact);
  return { text: fields, compacted };
}

/** Same rules as the API: every token must appear (case-insensitive, partial) in some field. */
export function matchesProduct(product: SearchableProduct, query: string): boolean {
  const tokens = searchTokens(query);
  if (tokens.length === 0) return true;
  const { text, compacted } = haystack(product);
  return tokens.every((token) => {
    const squeezed = compact(token);
    return (
      text.some((field) => field.includes(token)) ||
      (squeezed !== "" && compacted.some((field) => field.includes(squeezed)))
    );
  });
}

export function isExactCode(product: SearchableProduct, query: string): boolean {
  const value = query.trim().toLowerCase();
  return value !== "" && (product.barcode.toLowerCase() === value || product.sku.toLowerCase() === value);
}

function rank(product: SearchableProduct, query: string): number {
  if (isExactCode(product, query)) return 0;
  const first = searchTokens(query)[0] ?? "";
  return product.name.toLowerCase().startsWith(first) ? 1 : 2;
}

export function searchProducts<P extends SearchableProduct>(products: P[], query: string): ProductSearchHit<P>[] {
  if (searchTokens(query).length === 0) return products.map((product) => ({ product, match: "text" }));
  return products
    .filter((product) => matchesProduct(product, query))
    .sort((a, b) => rank(a, query) - rank(b, query) || a.name.localeCompare(b.name))
    .map((product) => ({ product, match: isExactCode(product, query) ? "exact" : "text" }));
}

/** Server hits win (identifier matches and live stock); local hits fill in when the server is unreachable. */
export function mergeHits<P extends SearchableProduct>(
  remote: ProductSearchHit<P>[] | null,
  local: ProductSearchHit<P>[],
): ProductSearchHit<P>[] {
  if (remote === null) return local;
  const seen = new Set(remote.map((hit) => hit.product.id));
  return [...remote, ...local.filter((hit) => !seen.has(hit.product.id))];
}
