import { isConsoleNavigation, isMarketingHost, isPublicNavigation } from "../pwa/cachePolicy";

/** A same-origin path the portal may reopen after sign-in. Public and auth pages are not destinations. */
export function safeNextPath(raw: string | null, hostname: string): string | null {
  if (raw === null || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\\") || raw.includes("://")) return null;
  let url: URL;
  try {
    url = new URL(raw, "https://axizpos.local");
  } catch {
    return null;
  }
  if (url.origin !== "https://axizpos.local") return null;
  const path = url.pathname;
  if (
    path === "/login" ||
    path === "/welcome" ||
    path.startsWith("/signup") ||
    path.startsWith("/kds") ||
    path === "/table" ||
    path.startsWith("/table/")
  ) {
    return null;
  }
  if (isPublicNavigation({ hostname, pathname: path }) || isConsoleNavigation({ pathname: path })) return null;
  return `${path}${url.search}`;
}

/** Where a signed-out visit to an application route should go. Null means stay on this URL. */
export function signedOutLocation(pathname: string, search: string, hostname: string): string | null {
  if (
    pathname === "/login" ||
    pathname === "/welcome" ||
    pathname.startsWith("/signup") ||
    pathname.startsWith("/kds") ||
    pathname === "/table" ||
    pathname.startsWith("/table/")
  ) {
    return null;
  }
  if (isPublicNavigation({ hostname, pathname }) || isConsoleNavigation({ pathname })) return null;
  const next = `${pathname}${search}`;
  return `/login?next=${encodeURIComponent(next)}`;
}

/** Where a signed-in visit to the login screen, or a public URL inside the installed app, should go. */
export function signedInLanding(pathname: string, search: string, hostname: string): string | null {
  const params = new URLSearchParams(search.startsWith("?") ? search.slice(1) : search);
  const next = safeNextPath(params.get("next"), hostname);
  if (pathname === "/login") return next ?? (isMarketingHost(hostname) ? "/dashboard" : "/");
  if (isMarketingHost(hostname) && isPublicNavigation({ hostname, pathname })) return "/dashboard";
  return null;
}
