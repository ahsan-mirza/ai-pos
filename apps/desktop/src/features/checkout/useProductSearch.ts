import {
  SEARCH_DEBOUNCE_MS,
  looksLikeIdentifier,
  mergeHits,
  searchProducts,
  searchTokens,
  type ProductSearchHit,
  type ProductUpsert,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { searchProductsRemote } from "../../lib/api";
import { inTauri, searchProductsLocal, searchProductsViaShell } from "../../lib/tauri";

export type Hit = ProductSearchHit<ProductUpsert>;

const REMOTE_TIMEOUT_MS = 4000;

const sellable = (hits: Hit[]) => hits.filter((hit) => !hit.product.is_ingredient);

async function localSearch(products: ProductUpsert[], query: string): Promise<Hit[]> {
  return sellable(inTauri() ? await searchProductsLocal(query) : searchProducts(products, query));
}

async function remoteSearch(query: string): Promise<Hit[] | null> {
  const request = inTauri() ? searchProductsViaShell(query) : searchProductsRemote(query);
  const timeout = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), REMOTE_TIMEOUT_MS));
  try {
    const hits = await Promise.race([request, timeout]);
    return hits === null ? null : sellable(hits);
  } catch {
    return null;
  }
}

/**
 * Universal product search: name, model, barcode, SKU, category, and brand match locally (SQLite in Tauri,
 * in memory in the browser) so results appear while offline; the API adds IMEI/serial matches and live stock.
 */
export function useProductSearch(query: string, products: ProductUpsert[]) {
  const [debounced, setDebounced] = useState(query);
  const [hits, setHits] = useState<Hit[]>(() => searchProducts(products, ""));
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    if (searchTokens(debounced).length === 0) {
      setHits(searchProducts(products, ""));
      setSearching(false);
      return;
    }
    setSearching(true);
    void localSearch(products, debounced).then((local) => {
      if (cancelled) return;
      setHits(local);
      void remoteSearch(debounced).then((remote) => {
        if (cancelled) return;
        setHits(mergeHits(remote, local));
        setSearching(false);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [debounced, products]);

  /** Immediate lookup for Enter / scanner input, bypassing the debounce. */
  const resolve = useCallback(
    async (value: string): Promise<Hit[]> => {
      const local = await localSearch(products, value);
      const needsServer = looksLikeIdentifier(value) && !local.some((hit) => hit.match === "exact");
      if (!needsServer) return local;
      return mergeHits(await remoteSearch(value), local);
    },
    [products],
  );

  return {
    hits,
    debouncedQuery: debounced,
    searching: searching || query !== debounced,
    resolve,
  };
}
