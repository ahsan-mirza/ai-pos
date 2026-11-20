/**
 * Which public paths may be indexed. Private application routes stay out of the sitemap.
 * robots.txt still lists a short disallow set. noindex on the portal shell is what Google should observe.
 */

export const SITE_ORIGIN = "https://axizpos.com";

export const INDEXABILITY = {
  public: "PUBLIC — SHOULD BE INDEXED",
  private: "PRIVATE — SHOULD NOT BE INDEXED",
  duplicate: "DUPLICATE — CANONICALIZE",
  redirect: "REDIRECT — CONSOLIDATE",
  invalid: "INVALID — REMOVE FROM SITEMAP",
  awaiting: "AWAITING URL EVIDENCE",
} as const;

export type Indexability = (typeof INDEXABILITY)[keyof typeof INDEXABILITY];

/** HTML routes whose shell is noindex. Crawl is allowed so Google can see that tag. */
export const PRIVATE_HTML_PREFIXES = [
  "/login",
  "/signup",
  "/welcome",
  "/demo",
  "/kds",
  "/table",
  "/m",
  "/inventory",
  "/dashboard",
  "/account",
  "/subscription",
  "/terminals",
  "/customers",
  "/sales",
  "/fulfillment",
  "/sales-orders",
  "/reorders",
  "/rentals",
  "/repairs",
  "/returns",
  "/users",
  "/warranties",
  "/margin",
  "/expenses",
  "/payables",
  "/consignment",
  "/staff",
  "/assistant",
  "/accounting",
  "/bank",
  "/insights",
  "/sales-insights",
  "/reports",
  "/einvoicing",
  "/analytics",
  "/promotions",
  "/trade-ins",
  "/store-credit",
  "/gift-cards",
  "/payments",
  "/cheques",
  "/shifts",
  "/reach",
  "/stores",
  "/roles",
  "/settings",
  "/registers",
  "/downloads",
  "/deliveries",
  "/admin",
  "/forgot-password",
  "/recover-store-code",
  "/admin74246",
] as const;

/** Not HTML documents. Blocking them does not hide a noindex tag Google needs to read. */
export const NON_HTML_DISALLOW = ["/api/", "/admin74246/"] as const;

/**
 * Current robots.txt disallow lines.
 * HTML sign-in routes stay listed until the Search Console URLs are known.
 * Removing them would change crawl reporting for unclassified URLs.
 */
export const ROBOTS_DISALLOW = [
  "/admin74246/",
  "/api/",
  "/login",
  "/signup",
  "/forgot-password",
  "/recover-store-code",
  "/dashboard",
] as const;

/** Paths that are not marketing pages. They 404 with noindex and stay out of the sitemap. */
export const UNPUBLISHED_PATHS = ["/pharmacy-pos", "/privacy", "/about", "/terms", "/refund", "/home"] as const;

/** One hop to a canonical marketing URL. */
export const CONSOLIDATED_REDIRECTS: Readonly<Record<string, string>> = {
  "/supermarket-pos": "/grocery-pos",
  "/home-2": "/",
  "/home-3": "/",
  "/pricing": "/#pricing",
  "/solutions": "/#solutions",
  "/features": "/#features",
  "/industries": "/#industries",
  "/contact": "/#contact",
  "/ai": "/#intelligence",
  "/copilot": "/#intelligence",
};

export function normalizePath(path: string): string {
  const bare = path.split("?")[0]?.split("#")[0] ?? "/";
  if (bare.length > 1 && bare.endsWith("/")) return bare.replace(/\/+$/, "");
  return bare || "/";
}

export function isPrivatePath(path: string): boolean {
  const normalized = normalizePath(path);
  return PRIVATE_HTML_PREFIXES.some((prefix) => normalized === prefix || normalized.startsWith(`${prefix}/`));
}

export function isUnpublishedPath(path: string): boolean {
  const normalized = normalizePath(path);
  return UNPUBLISHED_PATHS.some((item) => normalized === item);
}

export function classifyPath(path: string, publicPaths: ReadonlySet<string>): Indexability {
  const withoutHash = path.split("#")[0] ?? "/";
  if (withoutHash.includes("?")) return INDEXABILITY.duplicate;
  const raw = withoutHash === "" ? "/" : withoutHash;
  if (raw.length > 1 && raw.endsWith("/")) {
    const trimmed = raw.replace(/\/+$/, "");
    if (publicPaths.has(trimmed) || trimmed in CONSOLIDATED_REDIRECTS) return INDEXABILITY.redirect;
  }
  const normalized = normalizePath(raw);
  if (normalized in CONSOLIDATED_REDIRECTS) return INDEXABILITY.redirect;
  if (isUnpublishedPath(normalized)) return INDEXABILITY.invalid;
  if (isPrivatePath(normalized) || normalized === "/index.html") return INDEXABILITY.private;
  if (publicPaths.has(normalized)) return INDEXABILITY.public;
  if (normalized.startsWith("/hardware/") || normalized.startsWith("/ar/hardware/")) return INDEXABILITY.duplicate;
  return INDEXABILITY.invalid;
}

export function robotsDisallowBlock(): string {
  return ROBOTS_DISALLOW.map((path) => `Disallow: ${path}`).join("\n");
}
