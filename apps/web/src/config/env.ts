function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable ${name}. Check the repo-root env file (.env, .env.dev, or .env.production).`);
  }
  return value.trim();
}

const STORE_CODE_KEY = "ai-pos.store-code";

const TENANT_BASE_DOMAINS = (import.meta.env.VITE_TENANT_BASE_DOMAINS ?? "qios.ae,localhost")
  .split(",")
  .map((domain) => domain.trim().toLowerCase().replace(/^\./, ""))
  .filter((domain) => domain !== "");

/** "client1.qios.ae", "client1.dev.qios.ae" or "client1.localhost" when the portal is opened on a store subdomain. */
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

/** Subdomain, then the dev default, then the store code saved at sign-in. */
function tenantDomainNow(): string | null {
  return tenantHost() ?? configuredTenant ?? rememberedStoreCode();
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

/** The domain stores live under: the bare host we are on, the parent of a store subdomain, or the first configured. */
function tenantBaseDomain(): string {
  const host = typeof window === "undefined" ? "" : window.location.hostname.toLowerCase();
  return (
    TENANT_BASE_DOMAINS.find((base) => host === base || host.endsWith(`.${base}`)) ?? TENANT_BASE_DOMAINS[0] ?? "localhost"
  );
}

/** "client1.qios.ae" on the current scheme and port, e.g. http://client1.localhost:5173 in dev. */
function tenantPortalUrl(slug: string): string {
  const { protocol, port } = window.location;
  return `${protocol}//${slug}.${tenantBaseDomain()}${port ? `:${port}` : ""}`;
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
};
