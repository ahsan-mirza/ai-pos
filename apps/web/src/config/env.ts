function required(name: keyof ImportMetaEnv): string {
  const value = import.meta.env[name];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required environment variable ${name}. Check apps/web/.env.${import.meta.env.MODE}.`);
  }
  return value.trim();
}

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
const tenantDomain =
  tenantHost() ?? (typeof rawDefaultTenant === "string" && rawDefaultTenant.trim() !== "" ? rawDefaultTenant.trim() : null);
const tenantSlug = tenantDomain?.split(".")[0] ?? null;

/** VITE_API_BASE_URL may contain {tenant} (https://{tenant}.qios.ae) to follow the portal's subdomain. */
function requiredUrl(name: keyof ImportMetaEnv): string {
  const value = required(name)
    .replace("{tenant}", tenantSlug ?? "www")
    .replace(/\/$/, "");
  if (!/^https?:\/\//.test(value)) {
    throw new Error(`${name} must be an absolute http(s) URL.`);
  }
  return value;
}

const defaultCurrency = required("VITE_DEFAULT_CURRENCY").toUpperCase();
if (!/^[A-Z]{3}$/.test(defaultCurrency)) {
  throw new Error("VITE_DEFAULT_CURRENCY must be a 3-letter ISO code.");
}

/** Signup runs on the bare domain, so a {tenant} host collapses to it (https://{tenant}.qios.ae -> https://qios.ae). */
const signupApiBaseUrl = required("VITE_API_BASE_URL")
  .replace("{tenant}.", "")
  .replace("{tenant}", "www")
  .replace(/\/$/, "");

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
  apiBaseUrl: requiredUrl("VITE_API_BASE_URL"),
  signupApiBaseUrl,
  defaultCurrency,
  /** Sent as X-Tenant-Domain on every API call; null on a single-tenant install. */
  tenantDomain,
  /** True when the portal was opened on a store subdomain rather than the bare domain. */
  onTenantHost: tenantHost() !== null,
  tenantBaseDomain,
  tenantPortalUrl,
};
