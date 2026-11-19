import { describe, expect, it, beforeEach } from "vitest";
import type { ProductUpsert } from "@ai-pos/shared-types";
import {
  blocksCatalogueAdd,
  catalogueIdentity,
  catalogueLayoutClass,
  catalogueStockLabel,
} from "./cataloguePresentation";
import {
  clearCataloguePreferenceMemory,
  planCatalogueSync,
  readPreference,
  reconcileCatalogueView,
  reduceCatalogueSession,
  resetCataloguePreferences,
  saveCatalogueView,
  setDurableCatalogueStore,
  storedCatalogueView,
  writePreference,
  type CataloguePreference,
  type CatalogueTransport,
  type RemoteCatalogue,
} from "./cataloguePreference";
const tenant = "tenant-a";

function memoryStorage() {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => {
      map.set(key, value);
    },
    removeItem: (key: string) => {
      map.delete(key);
    },
  };
}

function preference(userId: string, value: CataloguePreference["value"], updatedAt: string, dirty = false): CataloguePreference {
  return { tenantId: tenant, userId, value, updatedAt, revision: 1, dirty };
}

function product(stock: number, extra: Partial<ProductUpsert> = {}): ProductUpsert {
  return {
    id: "p1",
    store_id: "store",
    sku: extra.sku ?? "MED-001",
    barcode: extra.barcode ?? "6280000000011",
    name: extra.name ?? "Acceptance Medicine A",
    category: extra.category ?? "OTC",
    price_cents: 1500,
    currency: "AED",
    is_serialized: false,
    stock_quantity: stock,
    ...extra,
  };
}

beforeEach(() => {
  resetCataloguePreferences(memoryStorage());
});

describe("catalogue view preference", () => {
  it("defaults to grid until a cashier chooses", () => {
    expect(storedCatalogueView(tenant, "user-a")).toBe("grid");
    expect(planCatalogueSync(null, null).view).toBe("grid");
  });

  it("keeps each cashier and tenant on their own view", () => {
    writePreference(preference("user-a", "grid", "2026-11-19T10:00:00Z"));
    writePreference(preference("user-b", "list", "2026-11-19T10:05:00Z"));
    writePreference({ ...preference("user-a", "compact", "2026-11-19T10:06:00Z"), tenantId: "tenant-b" });
    expect(readPreference(tenant, "user-a")?.value).toBe("grid");
    expect(readPreference(tenant, "user-b")?.value).toBe("list");
    expect(readPreference("tenant-b", "user-a")?.value).toBe("compact");
  });

  it("restores the saved view after the in-memory copy is cleared", () => {
    writePreference(preference("user-a", "compact", "2026-11-19T10:00:00Z"));
    clearCataloguePreferenceMemory();
    expect(storedCatalogueView(tenant, "user-a")).toBe("compact");
    expect(readPreference(tenant, "user-a")?.value).toBe("compact");
  });

  it("clears the visible cashier on sign-out and does not delete the saved view", () => {
    writePreference(preference("user-a", "list", "2026-11-19T10:00:00Z"));
    const signedOut = reduceCatalogueSession({ userId: "user-a", view: "list" }, { type: "sign_out" });
    expect(signedOut).toEqual({ userId: null, view: "grid" });
    expect(readPreference(tenant, "user-a")?.value).toBe("list");
    const next = reduceCatalogueSession(signedOut, { type: "sign_in", userId: "user-b", stored: "compact" });
    expect(next).toEqual({ userId: "user-b", view: "compact" });
    const back = reduceCatalogueSession({ userId: null, view: "grid" }, { type: "sign_in", userId: "user-a", stored: "list" });
    expect(back.view).toBe("list");
  });

  it("keeps search, category, and the cart when the view changes", () => {
    const sale = { query: "med", category: "OTC", cartLines: 2 };
    const view = reduceCatalogueSession({ userId: "user-a", view: "grid" }, { type: "choose", view: "list" }).view;
    expect({ ...sale, view }).toEqual({ query: "med", category: "OTC", cartLines: 2, view: "list" });
    expect(reduceCatalogueSession({ userId: "user-a", view: "list" }, { type: "choose", view: "compact" }).view).toBe("compact");
  });

  it("saves offline and sends that view when the account is reachable again", async () => {
    const disk = new Map<string, CataloguePreference>();
    setDurableCatalogueStore({
      async read(tenantId, userId) {
        return disk.get(`${tenantId}:${userId}`) ?? null;
      },
      async write(row) {
        disk.set(`${row.tenantId}:${row.userId}`, row);
      },
    });
    const offline: CatalogueTransport = {
      async read() {
        return null;
      },
      async write() {
        return null;
      },
    };
    expect(await saveCatalogueView(tenant, "user-a", "list", offline)).toBe("list");
    expect(disk.get(`${tenant}:user-a`)).toMatchObject({ value: "list", dirty: true });
    clearCataloguePreferenceMemory();
    expect(await reconcileCatalogueView(tenant, "user-a", offline)).toBe("list");

    let remote: RemoteCatalogue | null = null;
    const online: CatalogueTransport = {
      async read() {
        return remote ?? { product_catalogue_view: "grid", updated_at: null, revision: 0 };
      },
      async write(local) {
        remote = { product_catalogue_view: local.value, updated_at: "2026-11-19T12:00:00.000Z", revision: 4 };
        return remote;
      },
    };
    expect(await reconcileCatalogueView(tenant, "user-a", online)).toBe("list");
    expect(disk.get(`${tenant}:user-a`)).toMatchObject({ value: "list", dirty: false, revision: 4 });
    expect(await saveCatalogueView(tenant, "user-b", "compact", offline)).toBe("compact");
    expect(readPreference(tenant, "user-a")?.value).toBe("list");
    expect(readPreference(tenant, "user-b")?.value).toBe("compact");
  });

  it("keeps the newer view when the account and the register disagree", async () => {
    writePreference(preference("user-a", "grid", "2026-11-19T09:00:00.000Z", true));
    const remote: RemoteCatalogue = { product_catalogue_view: "compact", updated_at: "2026-11-19T11:00:00.000Z", revision: 3 };
    const transport: CatalogueTransport = {
      async read() {
        return remote;
      },
      async write() {
        throw new Error("the older local view must not be pushed");
      },
    };
    expect(await reconcileCatalogueView(tenant, "user-a", transport)).toBe("compact");
    expect(readPreference(tenant, "user-a")).toMatchObject({ value: "compact", dirty: false });

    writePreference(preference("user-b", "list", "2026-11-19T12:00:00.000Z", true));
    let pushed: string | null = null;
    const newerLocal: CatalogueTransport = {
      async read() {
        return { product_catalogue_view: "grid", updated_at: "2026-11-19T08:00:00.000Z", revision: 1 };
      },
      async write(local) {
        pushed = local.value;
        return { product_catalogue_view: local.value, updated_at: "2026-11-19T12:00:01.000Z", revision: 5 };
      },
    };
    expect(await reconcileCatalogueView(tenant, "user-b", newerLocal)).toBe("list");
    expect(pushed).toBe("list");
  });
});

describe("catalogue presentation", () => {
  it("uses a responsive grid instead of a fixed column count", () => {
    expect(catalogueLayoutClass("grid")).toContain("auto-fill");
    expect(catalogueLayoutClass("grid")).not.toContain("grid-cols-");
    expect(catalogueLayoutClass("compact")).toContain("auto-fill");
    expect(catalogueLayoutClass("compact")).not.toContain("grid-cols-");
    expect(catalogueLayoutClass("list")).toContain("flex-col");
    expect(catalogueLayoutClass("list")).not.toContain("auto-fill");
  });

  it("shows only the sku, barcode, and category the product already has", () => {
    expect(catalogueIdentity(product(5))).toBe("MED-001 · 6280000000011 · OTC");
    expect(catalogueIdentity(product(5, { barcode: "  ", category: "" }))).toBe("MED-001");
    expect(catalogueStockLabel(product(0), false)).toBe("Out of stock");
    expect(catalogueStockLabel(product(5), false)).toBe("5 Pieces");
    expect(catalogueStockLabel(product(0, { has_recipe: true }), true)).toBeNull();
    expect(blocksCatalogueAdd(product(0))).toBe(true);
    expect(blocksCatalogueAdd(product(5))).toBe(false);
    expect(blocksCatalogueAdd(product(0, { is_service: true }))).toBe(false);
  });
});
