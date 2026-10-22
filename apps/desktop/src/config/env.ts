function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable ${name}. Check apps/desktop/.env.${import.meta.env.MODE}.`);
  }
  return value.trim();
}

const apiBaseUrl = required("VITE_API_BASE_URL").replace(/\/$/, "");
if (!/^https?:\/\//.test(apiBaseUrl)) {
  throw new Error("VITE_API_BASE_URL must be an absolute http(s) URL.");
}

const syncIntervalMs = Number(required("VITE_SYNC_INTERVAL_MS"));
if (!Number.isInteger(syncIntervalMs) || syncIntervalMs < 1000) {
  throw new Error("VITE_SYNC_INTERVAL_MS must be an integer of at least 1000.");
}

const rawApiKey = import.meta.env.VITE_API_KEY;
const apiKey = typeof rawApiKey === "string" && rawApiKey.trim() !== "" ? rawApiKey.trim() : null;
if (apiKey !== null && apiKey.length < 16) {
  throw new Error("VITE_API_KEY must be at least 16 characters.");
}

const DEFAULT_STORE_ID = "00000000-0000-4000-8000-000000000001";
const rawStoreId = import.meta.env.VITE_STORE_ID;
const storeId = typeof rawStoreId === "string" && rawStoreId.trim() !== "" ? rawStoreId.trim() : DEFAULT_STORE_ID;

const rawTenant = import.meta.env.VITE_TENANT_DOMAIN;
const tenantDomain = typeof rawTenant === "string" && rawTenant.trim() !== "" ? rawTenant.trim().toLowerCase() : null;

export const env = {
  apiBaseUrl,
  apiKey,
  deviceId: required("VITE_DEVICE_ID"),
  /** The branch this register sells from. Activated Tauri registers replace it with their store at startup. */
  storeId,
  /** Tenant the browser preview talks to (X-Tenant-Domain). */
  tenantDomain,
  syncIntervalMs,
};

/** Headers the browser preview sends; the Tauri shell adds the activated register's own from Rust. */
export function previewHeaders(): Record<string, string> {
  const headers: Record<string, string> = {};
  if (env.apiKey !== null) headers["X-Terminal-Token"] = env.apiKey;
  if (env.tenantDomain !== null) headers["X-Tenant-Domain"] = env.tenantDomain;
  return headers;
}
