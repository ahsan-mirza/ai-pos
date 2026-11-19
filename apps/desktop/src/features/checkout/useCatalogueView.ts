import { useCallback, useEffect, useRef, useState } from "react";
import { env, previewHeaders } from "../../config/env";
import { RetailRequestError, retailCall } from "../../lib/retailClient";
import { inTauri, readCataloguePreference, writeCataloguePreference } from "../../lib/tauri";
import { currentAccessToken } from "../auth/session";
import {
  parseCatalogueView,
  readPreference,
  reconcileCatalogueView,
  reduceCatalogueSession,
  saveCatalogueView,
  setDurableCatalogueStore,
  storedCatalogueView,
  type CataloguePreference,
  type CatalogueTransport,
  type CatalogueView,
  type RemoteCatalogue,
} from "./cataloguePreference";

const READ_PATH = "/api/v1/users/me/preferences";
const WRITE_PATH = "/api/v1/users/me/preferences/product-catalogue-view";

export function catalogueTenantId(): string {
  const domain = env.tenantDomain?.trim();
  return domain ? domain : "local";
}

function asRemote(value: unknown): RemoteCatalogue | null {
  if (!value || typeof value !== "object") return null;
  const row = value as Record<string, unknown>;
  const view = parseCatalogueView(row.product_catalogue_view);
  if (!view) return null;
  return {
    product_catalogue_view: view,
    updated_at: typeof row.updated_at === "string" ? row.updated_at : null,
    revision: typeof row.revision === "number" ? row.revision : 0,
  };
}

async function browserPreference(method: "GET" | "PUT", path: string, body?: unknown): Promise<RemoteCatalogue | null> {
  const token = currentAccessToken();
  if (!token) return null;
  try {
    const response = await fetch(`${env.apiBaseUrl}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...previewHeaders(),
        Authorization: `Bearer ${token}`,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) return null;
    return asRemote(await response.json());
  } catch {
    return null;
  }
}

export function liveCatalogueTransport(): CatalogueTransport {
  return {
    async read() {
      try {
        if (inTauri()) return asRemote(await retailCall<unknown>("GET", READ_PATH));
        return browserPreference("GET", READ_PATH);
      } catch (caught) {
        if (caught instanceof RetailRequestError) return null;
        return null;
      }
    },
    async write(local) {
      const body = { product_catalogue_view: local.value, updated_at: local.updatedAt };
      try {
        if (inTauri()) return asRemote(await retailCall<unknown>("PUT", WRITE_PATH, body));
        return browserPreference("PUT", WRITE_PATH, body);
      } catch (caught) {
        if (caught instanceof RetailRequestError) return null;
        return null;
      }
    },
  };
}

function preferenceFromRow(tenantId: string, userId: string, row: Awaited<ReturnType<typeof readCataloguePreference>>): CataloguePreference | null {
  if (!row) return null;
  const value = parseCatalogueView(row.value);
  if (!value) return null;
  return {
    tenantId,
    userId,
    value,
    updatedAt: row.updated_at,
    revision: row.revision,
    dirty: row.dirty,
  };
}

if (inTauri()) {
  setDurableCatalogueStore({
    async read(tenantId, userId) {
      return preferenceFromRow(tenantId, userId, await readCataloguePreference(tenantId, userId));
    },
    async write(preference) {
      await writeCataloguePreference({
        tenantId: preference.tenantId,
        userId: preference.userId,
        value: preference.value,
        updatedAt: preference.updatedAt,
        revision: preference.revision,
        dirty: preference.dirty,
      });
    },
  });
}

/** Restores this cashier's view immediately, then reconciles it with the account when online. */
export function useCatalogueView(userId: string): { view: CatalogueView; setView: (view: CatalogueView) => void } {
  const tenantId = catalogueTenantId();
  const [state, setState] = useState(() =>
    reduceCatalogueSession(
      { userId: null, view: "grid" },
      { type: "sign_in", userId, stored: storedCatalogueView(tenantId, userId) },
    ),
  );
  if (state.userId !== userId) {
    setState(
      reduceCatalogueSession(state, {
        type: "sign_in",
        userId,
        stored: readPreference(tenantId, userId)?.value ?? "grid",
      }),
    );
  }
  const request = useRef(0);
  useEffect(() => {
    let cancelled = false;
    const token = ++request.current;
    void reconcileCatalogueView(tenantId, userId, liveCatalogueTransport()).then((next) => {
      if (cancelled || request.current !== token) return;
      setState((current) => (current.userId === userId ? reduceCatalogueSession(current, { type: "adopt", view: next }) : current));
    });
    return () => {
      cancelled = true;
    };
  }, [tenantId, userId]);

  const setView = useCallback(
    (next: CatalogueView) => {
      const token = ++request.current;
      setState((current) => reduceCatalogueSession(current, { type: "choose", view: next }));
      void saveCatalogueView(tenantId, userId, next, liveCatalogueTransport()).then((winning) => {
        if (request.current !== token) return;
        setState((current) => (current.userId === userId ? reduceCatalogueSession(current, { type: "adopt", view: winning }) : current));
      });
    },
    [tenantId, userId],
  );

  return { view: state.view, setView };
}
