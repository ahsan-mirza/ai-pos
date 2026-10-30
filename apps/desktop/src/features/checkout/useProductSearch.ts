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
import { registerCapabilities } from "../../lib/capabilities";
import { productFitsRegister } from "../../lib/industry";
import { inTauri, searchProductsLocal, searchProductsViaShell } from "../../lib/tauri";

export type Hit = ProductSearchHit<ProductUpsert>;

const REMOTE_TIMEOUT_MS = 4000;

const offered = (hits: Hit[], hideInactive: boolean) => {
  const profile = registerCapabilities().profile;
  return hits.filter(
    (hit) =>
      !hit.product.is_ingredient &&
      productFitsRegister(hit.product, profile) &&
      (!hideInactive || hit.product.is_active !== false),
  );
};

const sellable = (hits: Hit[]) => offered(hits, true);

async function localSearch(products: ProductUpsert[], query: string): Promise<Hit[]> {
  return sellable(inTauri() ? await searchProductsLocal(query) : searchProducts(products, query));
}

async function remoteSearch(query: string, hideInactive: boolean): Promise<Hit[] | null> {
  const request = inTauri() ? searchProductsViaShell(query) : searchProductsRemote(query);
  const timeout = new Promise<null>((resolve) => window.setTimeout(() => resolve(null), REMOTE_TIMEOUT_MS));
  try {
    const hits = await Promise.race([request, timeout]);
    return hits === null ? null : offered(hits, hideInactive);
  } catch {
    return null;
  }
}

/** A scanned inactive barcode still resolves, so the register can say it cannot be sold. */
const scanned = (hits: Hit[]) =>
  hits.filter((hit) => hit.product.is_active !== false || hit.match === "exact" || hit.match === "identifier");

/**
 * Universal product search: name, model, barcode, SKU, category, and brand match locally (SQLite in Tauri,
 * in memory in the browser) so results appear while offline; the API adds IMEI/serial matches and live stock.
 */
export function useProductSearch(query: string, products: ProductUpsert[]) {
  const [debounced, setDebounced] = useState(query);
  const [hits, setHits] = useState<Hit[]>(() => sellable(searchProducts(products, "")));
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(query), SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    if (searchTokens(debounced).length === 0) {
      setHits(sellable(searchProducts(products, "")));
      setSearching(false);
      return;
    }
    setSearching(true);
    void localSearch(products, debounced).then((local) => {
      if (cancelled) return;
      setHits(local);
      void remoteSearch(debounced, true).then((remote) => {
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
      const local = offered(inTauri() ? await searchProductsLocal(value) : searchProducts(products, value), false);
      const needsServer = looksLikeIdentifier(value) && !local.some((hit) => hit.match === "exact");
      if (!needsServer) return scanned(local);
      return scanned(mergeHits(await remoteSearch(value, false), local));
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
