import seed from "@ai-pos/catalog/seed.json";
import type { ProductUpsert, StoreUpsert } from "@ai-pos/shared-types";
import { useEffect } from "react";
import { catalogRevision as fetchCatalogRevision, listProducts } from "../../lib/api";
import { beginSync } from "../../lib/syncActivity";
import { cachedProducts, catalogRevision as readDesktopRevision, inTauri, refreshProducts } from "../../lib/tauri";
import { registerCapabilities } from "../../lib/capabilities";
import { productFitsRegister } from "../../lib/industry";
import { GIFT_CARD_SKU } from "./cart";
import { LINK_RESTORED_EVENT } from "../sync/autoReconnect";
import { activeStore, businessCurrency, syncBusinessCurrency } from "./currency";
import { refreshMenu } from "./menu";

/** Store identity only; its currency comes from `activeStore()` / `useBusinessCurrency()`. */
export const store: StoreUpsert = activeStore();
export const taxRateBps: number = seed.tax_rate_bps;

/**
 * Rows bundled in seed.json. An empty database used to insert them, and checkout painted them
 * while the store catalogue was still downloading. They are not a catalogue for any tenant.
 */
export const BUNDLED_DEMO_IDS = new Set([
  "00000000-0000-4000-8000-000000000010",
  "00000000-0000-4000-8000-000000000011",
  "00000000-0000-4000-8000-000000000012",
  "00000000-0000-4000-8000-000000000013",
  "00000000-0000-4000-8000-000000000014",
]);

const CACHE_PREFIX = "ai-pos.pos.catalog.";
const OFFLINE_NOTICE = "Unable to refresh the catalogue. Showing the last synchronized products.";
const UNAVAILABLE_NOTICE = "Products could not be loaded. Check your connection and retry.";

export function withoutBundledDemo<T extends { id: string }>(products: readonly T[]): T[] {
  return products.filter((product) => !BUNDLED_DEMO_IDS.has(product.id));
}

export interface Catalog {
  products: ProductUpsert[];
  source: "api" | "cache";
  message: string | null;
  /** The server cursor matches this register. Keep the products already on screen. */
  unchanged?: boolean;
}

/** A failed refresh keeps the products already on screen and stays silent. A successful empty catalogue is a real empty catalogue. */
export function mergeCatalog(current: readonly ProductUpsert[], next: Catalog): Catalog {
  if (next.products.length === 0 && next.message && current.length > 0) {
    return { products: [...current], source: "cache", message: null };
  }
  if (next.products.length > 0 && next.message === OFFLINE_NOTICE) {
    return { ...next, message: null };
  }
  return next;
}

function cacheKey(): string {
  return `${CACHE_PREFIX}${store.id}`;
}

function readRemembered(): ProductUpsert[] | null {
  try {
    const raw = localStorage.getItem(cacheKey());
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { products?: ProductUpsert[] };
    const products = withoutBundledDemo(parsed.products ?? []).filter((product) => product?.id && product.name);
    return products.length > 0 ? products : null;
  } catch {
    return null;
  }
}

function remember(products: readonly ProductUpsert[]): void {
  try {
    localStorage.setItem(cacheKey(), JSON.stringify({ products: withoutBundledDemo(products) }));
  } catch {
    // A full disk keeps the in-memory catalogue. The next successful sync tries again.
  }
}

function present(products: readonly ProductUpsert[]): ProductUpsert[] {
  const profile = registerCapabilities().profile;
  const currency = businessCurrency();
  return withoutBundledDemo(products)
    .filter((product) => !product.is_ingredient && product.sku !== GIFT_CARD_SKU && productFitsRegister(product, profile))
    .map((product) => ({ ...product, currency }));
}

/** Last catalogue this device stored. Empty until a store catalogue has synced. */
export function openingCatalog(): Catalog {
  return { products: present(readRemembered() ?? []), source: "cache", message: null };
}

/** SQLite on the desktop app, otherwise the same device cache checkout paints on the first frame. */
export async function localCatalog(): Promise<Catalog | null> {
  try {
    const rows = inTauri() ? await cachedProducts() : (readRemembered() ?? []);
    const products = present(rows);
    if (products.length === 0) return null;
    return { products, source: "cache", message: null };
  } catch {
    return null;
  }
}

let inflight: Promise<Catalog> | null = null;

async function fetchCatalog(): Promise<Catalog> {
  const started = performance.now();
  void syncBusinessCurrency();
  let catalog: Catalog;
  if (inTauri()) {
    const snapshot = await refreshProducts();
    if (snapshot.unchanged) {
      catalog = {
        products: withoutBundledDemo(snapshot.products),
        source: "api",
        message: null,
        unchanged: true,
      };
    } else {
      const products = withoutBundledDemo(snapshot.products);
      if (snapshot.source === "api") remember(products);
      catalog = {
        products,
        source: snapshot.source === "api" ? "api" : "cache",
        message: snapshot.source === "api" || products.length > 0 ? null : UNAVAILABLE_NOTICE,
      };
    }
  } else {
    try {
      const products = withoutBundledDemo(await listProducts());
      remember(products);
      catalog = { products, source: "api", message: null };
    } catch {
      const cached = readRemembered();
      catalog = cached
        ? { products: cached, source: "cache", message: null }
        : { products: [], source: "cache", message: UNAVAILABLE_NOTICE };
    }
  }
  const ready = { ...catalog, products: present(catalog.products), unchanged: catalog.unchanged };
  console.info(
    `[POS_API_PERF] endpoint=catalog source=${ready.source} count=${ready.products.length} total_ms=${Math.round(performance.now() - started)}`,
  );
  return ready;
}

export function loadCatalog(): Promise<Catalog> {
  if (inflight) return inflight;
  const end = beginSync();
  inflight = fetchCatalog().finally(() => {
    inflight = null;
    end();
  });
  return inflight;
}

/** Cheap cursor. Null when the register cannot reach the API; the local catalog stays as it is. */
export async function readCatalogRevision(): Promise<string | null> {
  try {
    if (inTauri()) return await readDesktopRevision();
    const body = await fetchCatalogRevision();
    return `${body.updated_at ?? ""}:${body.count}`;
  } catch {
    return null;
  }
}

const CATALOG_POLL_MS = 5_000;

/** Checkout and Orders listen for this after a portal commit has been applied. */
export const CATALOGUE_SYNC_EVENT = "pos-catalogue-sync";

let catalogueSyncing = false;
let catalogueSyncAgain = false;

/**
 * One refresh for a committed catalogue change. A second event during the refresh runs once more
 * after it finishes, so a burst does not stack requests and a late event is not dropped.
 * The sale queue is not read or written.
 */
export function requestCatalogueSync(): void {
  if (catalogueSyncing) {
    catalogueSyncAgain = true;
    return;
  }
  catalogueSyncing = true;
  catalogueSyncAgain = false;
  void (async () => {
    try {
      await syncBusinessCurrency().catch(() => undefined);
      await refreshMenu().catch(() => undefined);
    } finally {
      catalogueSyncing = false;
      window.dispatchEvent(new CustomEvent(CATALOGUE_SYNC_EVENT));
      if (catalogueSyncAgain) requestCatalogueSync();
    }
  })();
}

/**
 * While the register is online, reload the catalog only after the server cursor moves.
 * A failed check keeps the products already on screen and does not touch the offline sale queue.
 * A `catalogue.changed` frame from the register socket refreshes immediately.
 */
export function useCatalogUpdates(reload: () => void): void {
  useEffect(() => {
    let seen: string | null = null;
    let missed = false;
    let cancelled = false;
    const poll = async () => {
      const revision = await readCatalogRevision();
      if (cancelled) return;
      if (revision === null) {
        missed = true;
        return;
      }
      if (seen === null) {
        seen = revision;
        missed = false;
        return;
      }
      if (!missed && revision === seen) return;
      seen = revision;
      missed = false;
      requestCatalogueSync();
    };
    const onSync = () => reload();
    const onRestored = () => {
      missed = true;
      void poll();
    };
    void poll();
    const timer = window.setInterval(() => void poll(), CATALOG_POLL_MS);
    const again = () => void poll();
    const onReturn = () => reload();
    window.addEventListener("online", again);
    window.addEventListener("focus", again);
    window.addEventListener(LINK_RESTORED_EVENT, onRestored);
    window.addEventListener("pos-return-processed", onReturn);
    window.addEventListener(CATALOGUE_SYNC_EVENT, onSync);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("online", again);
      window.removeEventListener("focus", again);
      window.removeEventListener(LINK_RESTORED_EVENT, onRestored);
      window.removeEventListener("pos-return-processed", onReturn);
      window.removeEventListener(CATALOGUE_SYNC_EVENT, onSync);
    };
  }, [reload]);
}
