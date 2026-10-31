/** What the service worker is allowed to store. Live business data stays on the network. */

const BLOCKED_PATH = [/^\/api(?:\/|$)/, /^\/media(?:\/|$)/];

export function mayCacheRequest(pathname: string, hasAuthorization: boolean): boolean {
  if (hasAuthorization) return false;
  return !BLOCKED_PATH.some((rule) => rule.test(pathname));
}

/** Precache names belong to the app shell. Anything else is user-scoped and leaves on sign-out. */
export function isUserScopedCache(name: string): boolean {
  return name.startsWith("business-pro-user") || name.includes("api");
}
