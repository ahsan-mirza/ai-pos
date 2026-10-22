import {
  SEARCH_DEBOUNCE_MS,
  looksLikeIdentifier,
  mergeHits,
  searchProducts,
  searchTokens,
  type Product,
  type ProductSearchHit,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../../lib/api";

async function remoteSearch(query: string): Promise<ProductSearchHit[] | null> {
  try {
    const params = new URLSearchParams({ q: query, limit: "100" });
    return await apiGet<ProductSearchHit[]>(`/api/v1/products/search?${params.toString()}`);
  } catch {
    return null;
  }
}

/** Debounced universal search: instant local filtering, then API results (IMEI/serial matches) merged in. */
export function useProductSearch(query: string, products: Product[], live: boolean) {
  const [debounced, setDebounced] = useState(query);
  const [remote, setRemote] = useState<{ query: string; hits: ProductSearchHit[] | null } | null>(null);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    if (!live || searchTokens(debounced).length === 0) return;
    let cancelled = false;
    void remoteSearch(debounced).then((hits) => {
      if (!cancelled) setRemote({ query: debounced, hits });
    });
    return () => {
      cancelled = true;
    };
  }, [debounced, live]);

  const local = searchProducts(products, debounced);
  const remoteHits = remote !== null && remote.query === debounced ? remote.hits : null;
  const hits = searchTokens(debounced).length === 0 ? local : mergeHits(remoteHits, local);

  const resolve = useCallback(
    async (value: string): Promise<ProductSearchHit[]> => {
      const immediate = searchProducts(products, value);
      if (!live || !looksLikeIdentifier(value) || immediate.some((hit) => hit.match === "exact")) return immediate;
      return mergeHits(await remoteSearch(value), immediate);
    },
    [live, products],
  );

  return {
    hits,
    debouncedQuery: debounced,
    searching: query !== debounced || (live && searchTokens(debounced).length > 0 && remote?.query !== debounced),
    resolve,
  };
}
