import {
  Permission,
  type Availability,
  type Product,
  type ProductCosting,
  type ProductPurchaseHistory,
  type ProductSalesHistory,
  type ProductSerials,
  type SerialStatus,
  type StockMovement,
} from "@ai-pos/shared-types";
import { useCallback, useEffect, useState } from "react";
import { apiGet } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { message } from "./api";

export type Resource<T> =
  { state: "loading" } | { state: "ready"; data: T } | { state: "error"; message: string } | { state: "forbidden" };

const loading = { state: "loading" } as const;
const forbidden = { state: "forbidden" } as const;

function useResource<T>(path: string | null, allowed: boolean, version: number): Resource<T> {
  const [resource, setResource] = useState<Resource<T>>(loading);
  useEffect(() => {
    if (path === null) return;
    if (!allowed) {
      setResource(forbidden);
      return;
    }
    let cancelled = false;
    setResource(loading);
    apiGet<T>(path)
      .then((data) => {
        if (!cancelled) setResource({ state: "ready", data });
      })
      .catch((error: unknown) => {
        if (!cancelled) setResource({ state: "error", message: message(error, "Could not load this section.") });
      });
    return () => {
      cancelled = true;
    };
  }, [path, allowed, version]);
  return resource;
}

export interface SerialFilters {
  enabled: boolean;
  status: SerialStatus | null;
  query: string;
}

/** Everything the product drawer shows. Each section loads on its own, so one slow or forbidden
 * endpoint never blanks the others. Sales need reports access; purchase costs need inventory management. */
export function useProductDetails(productId: string | null, serialFilters: SerialFilters, refreshKey = 0) {
  const { can } = useAuth();
  const [local, setLocal] = useState(0);
  const reload = useCallback(() => setLocal((value) => value + 1), []);
  const version = local + refreshKey;
  const base = productId === null ? null : `/api/v1/products/${productId}`;

  const product = useResource<Product>(base, true, version);
  const availability = useResource<Availability>(
    productId === null ? null : `/api/v1/inventory/availability?product_id=${productId}`,
    true,
    version,
  );
  const sales = useResource<ProductSalesHistory>(
    base && `${base}/sales-history?limit=200`,
    can(Permission.PortalReportsRead),
    version,
  );
  const purchases = useResource<ProductPurchaseHistory>(
    base && `${base}/purchase-history?limit=200`,
    can(Permission.PortalInventoryManage),
    version,
  );
  const costing = useResource<ProductCosting>(
    base && `${base}/costing`,
    can(Permission.PortalInventoryManage),
    version,
  );
  const serialParams = new URLSearchParams({ limit: "500" });
  if (serialFilters.status) serialParams.set("status", serialFilters.status);
  if (serialFilters.query.trim()) serialParams.set("q", serialFilters.query.trim());
  const serials = useResource<ProductSerials>(
    base && `${base}/serials?${serialParams.toString()}`,
    serialFilters.enabled,
    version,
  );
  const movements = useResource<StockMovement[]>(base && `${base}/movements?limit=300`, true, version);

  return { product, availability, sales, purchases, costing, serials, movements, reload };
}
