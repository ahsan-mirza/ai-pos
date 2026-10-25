function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable ${name}. Check the repo-root env file (.env, .env.dev, or .env.production).`);
  }
  return value.trim();
}

const STORE_CODE_KEY = "ai-pos.store-code";

const TENANT_BASE_DOMAINS = (import.meta.env.VITE_TENANT_BASE_DOMAINS ?? "axizpos.com,localhost")
  .split(",")
  .map((domain) => domain.trim().toLowerCase().replace(/^\./, ""))
  .filter((domain) => domain !== "");

/** "client1.axizpos.com", "client1.dev.axizpos.com" or "client1.localhost" when the portal is opened on a store subdomain. */
function tenantHost(): string | null {
  const host = typeof window === "undefined" ? "" : window.location.hostname.toLowerCase();
  for (const base of TENANT_BASE_DOMAINS) {
    if (!host.endsWith(`.${base}`)) continue;
    const label = host.slice(0, -(base.length + 1));
    if (label !== "" && !label.includes(".") && label !== "www") return host;
  }
  return null;
}

const rawDefaultTenant = import.meta.env.VITE_DEFAULT_TENANT;
const configuredTenant =
  typeof rawDefaultTenant === "string" && rawDefaultTenant.trim() !== "" ? rawDefaultTenant.trim() : null;
const tenantSlug = (tenantHost() ?? configuredTenant)?.split(".")[0] ?? null;

/** Store code typed on the sign-in screen when the portal is opened by a public IP (no subdomain). */
function rememberedStoreCode(): string | null {
  if (typeof localStorage === "undefined") return null;
  const value = localStorage.getItem(STORE_CODE_KEY)?.trim().toLowerCase() ?? "";
  return value === "" ? null : value;
}

/** Subdomains stay off until each store has its own host. The slug is a store code on this site. */
const STORE_SUBDOMAINS = false;

/** A saved store code on this host, then the dev default. A store subdomain is used only when those hosts are on. */
function tenantDomainNow(): string | null {
  if (STORE_SUBDOMAINS) return tenantHost() ?? rememberedStoreCode() ?? configuredTenant;
  return rememberedStoreCode() ?? configuredTenant;
}

/** True on a production IP install: the sign-in screen must collect the store code. */
function needsStoreCode(): boolean {
  return tenantHost() === null && configuredTenant === null;
}

export function saveStoreCode(code: string): void {
  localStorage.setItem(STORE_CODE_KEY, code.trim().toLowerCase());
}

/** "same-origin" follows the address in the browser (http://<vm-public-ip>). "{tenant}" follows a subdomain. */
function resolveUrl(raw: string): string {
  if (raw === "same-origin") {
    return typeof window === "undefined" ? "http://127.0.0.1" : window.location.origin;
  }
  const value = raw.replace("{tenant}", tenantSlug ?? "www").replace(/\/$/, "");
  if (!/^https?:\/\//.test(value)) {
    throw new Error("VITE_API_BASE_URL must be an absolute http(s) URL or same-origin.");
  }
  return value;
}

function requiredUrl(name: keyof ImportMetaEnv): string {
  return resolveUrl(required(name));
}

const defaultCurrency = required("VITE_DEFAULT_CURRENCY").toUpperCase();
if (!/^[A-Z]{3}$/.test(defaultCurrency)) {
  throw new Error("VITE_DEFAULT_CURRENCY must be a 3-letter ISO code.");
}

/** Signup runs on the bare domain, so a {tenant} host collapses to it. */
function resolveSignupUrl(): string {
  const raw = required("VITE_API_BASE_URL");
  if (raw === "same-origin") return resolveUrl(raw);
  return raw.replace("{tenant}.", "").replace("{tenant}", "www").replace(/\/$/, "");
}

function isIpHost(value: string): boolean {
  const host = value.trim().replace(/^\[|\]$/g, "");
  if (/^\d{1,3}(\.\d{1,3}){3}$/.test(host)) {
    return host.split(".").every((part) => Number(part) <= 255);
  }
  return host.includes(":");
}

function pageHost(): string {
  return typeof window === "undefined" ? "" : window.location.hostname.toLowerCase();
}

/** The domain stores live under: a configured suffix, this host when it is a real domain, or localhost in development. */
function tenantBaseDomain(): string {
  const host = pageHost().replace(/^www\./, "");
  const configured = TENANT_BASE_DOMAINS.find((base) => host === base || host.endsWith(`.${base}`));
  if (configured) return configured;
  if (isIpHost(host)) return host;
  if (host !== "" && host !== "localhost" && !host.endsWith(".localhost")) return host;
  return TENANT_BASE_DOMAINS[0] ?? "localhost";
}

/** A public IP has no store subdomain. The portal stays on this host and sends the store code separately. */
function directHost(): boolean {
  const host = pageHost();
  return isIpHost(host) || isIpHost(tenantBaseDomain());
}

/** A public IP, or this product while store subdomains are off, keeps every store on this host. */
function storesShareThisHost(): boolean {
  return !STORE_SUBDOMAINS || directHost();
}

/** "client1.axizpos.com" on the current scheme and port, or this host itself when stores share it. */
function tenantPortalUrl(slug: string): string {
  if (storesShareThisHost()) return window.location.origin;
  const { protocol, port } = window.location;
  return `${protocol}//${slug}.${tenantBaseDomain()}${port ? `:${port}` : ""}`;
}

/** How the signup screen names the new store: a store code on this host, or a subdomain. */
function storeAddressLabel(slug: string): string {
  if (storesShareThisHost()) return slug;
  return `${slug}.${tenantBaseDomain()}`;
}

export const env = {
  get apiBaseUrl() {
    return requiredUrl("VITE_API_BASE_URL");
  },
  get signupApiBaseUrl() {
    return resolveSignupUrl();
  },
  defaultCurrency,
  /** Sent as X-Tenant-Domain on every API call. */
  get tenantDomain() {
    return tenantDomainNow();
  },
  /** True when the portal was opened on a store subdomain rather than the bare host or an IP. */
  get onTenantHost() {
    return tenantHost() !== null;
  },
  /** The sign-in screen asks for a store code because this host has no subdomain. */
  get needsStoreCode() {
    return needsStoreCode();
  },
  tenantBaseDomain,
  tenantPortalUrl,
  /** True when every store is opened on this host, with the store code sent to the API. */
  get storesShareThisHost() {
    return storesShareThisHost();
  },
  /** True when stores are reached on this IP, with the store code sent to the API. */
  get directHost() {
    return directHost();
  },
  storeAddressLabel,
};
