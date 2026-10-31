/** What the service worker is allowed to store. Live business data stays on the network. */

const BLOCKED_PATH = [/^\/api(?:\/|$)/, /^\/media(?:\/|$)/];

const MARKETING_HOSTS = new Set(["axizpos.com", "www.axizpos.com"]);

/** Public marketing pages. The portal service worker must not claim these navigations. */
export const PUBLIC_MARKETING_PATHS = [
  "/restaurant-pos",
  "/retail-pos",
  "/grocery-pos",
  "/cafe-pos",
  "/quick-service-pos",
  "/wholesale-pos",
  "/fashion-pos",
  "/electronics-pos",
  "/pos-software-uae",
];

const PUBLIC_PREFIXES = ["/site-assets/", "/pos/", "/brand/", "/portal/"];

export function isMarketingHost(hostname: string): boolean {
  return MARKETING_HOSTS.has(hostname.toLowerCase());
}

function barePath(pathname: string): string {
  if (pathname === "/") return "/";
  return pathname.replace(/\/+$/, "") || "/";
}

/** The public website. On a store host, `/` is the portal and is not public. */
export function isPublicNavigation(url: { hostname: string; pathname: string }): boolean {
  const path = barePath(url.pathname);
  if (PUBLIC_PREFIXES.some((prefix) => url.pathname.startsWith(prefix))) return true;
  if (path === "/robots.txt" || path === "/sitemap.xml") return true;
  if (PUBLIC_MARKETING_PATHS.includes(path)) return true;
  if (!isMarketingHost(url.hostname)) return false;
  return path === "/" || path === "/index.html";
}

/** Navigations the installed portal may open from its own shell. */
export function isPortalNavigation(url: { hostname: string; pathname: string }): boolean {
  return !isPublicNavigation(url);
}

/**
 * What a public marketing document should do with the portal service worker.
 * A normal browser tab lets the worker go. An installed app opens the portal instead.
 */
export function marketingWorkerAction(input: {
  hostname: string;
  pathname: string;
  standalone: boolean;
  controlled: boolean;
}): "leave" | "open-portal" | "none" {
  if (!isPublicNavigation(input)) return "none";
  if (input.standalone) {
    const path = barePath(input.pathname);
    if (path === "/" || path === "/index.html" || PUBLIC_MARKETING_PATHS.includes(path)) return "open-portal";
    return "none";
  }
  return input.controlled ? "leave" : "none";
}

export function mayCacheRequest(pathname: string, hasAuthorization: boolean, hostname = ""): boolean {
  if (hasAuthorization) return false;
  if (BLOCKED_PATH.some((rule) => rule.test(pathname))) return false;
  if (hostname !== "" && isPublicNavigation({ hostname, pathname })) return false;
  return true;
}

/** Precache names belong to the app shell. Anything else is user-scoped and leaves on sign-out. */
export function isUserScopedCache(name: string): boolean {
  return name.startsWith("business-pro-user") || name.includes("api");
}
