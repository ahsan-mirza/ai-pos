const MARKETING_HOSTS = new Set(["axizpos.com", "www.axizpos.com"]);

/** The public landing page owns `/` on the apex domain. The portal stays on every other host. */
export function onMarketingHost(): boolean {
  if (typeof window === "undefined") return false;
  return MARKETING_HOSTS.has(window.location.hostname.toLowerCase());
}

/** Dashboard. On axizpos.com this is not `/`, because that address is the landing page. */
export function portalHomePath(): string {
  return onMarketingHost() ? "/dashboard" : "/";
}

/** Sign-in. On axizpos.com `/` is the landing page, so the form lives at `/login`. */
export function portalSignInPath(): string {
  return onMarketingHost() ? "/login" : "/";
}
