import { isPublicNavigation, isUserScopedCache } from "./cachePolicy";
import { shouldApplyUpdate } from "./install";

/** How often an open portal asks the browser for a new service worker. */
export const APP_UPDATE_CHECK_MS = 60_000;

/** Drops caches that could hold a person's session. The precached shell stays. */
export async function clearUserCaches(): Promise<void> {
  if (typeof window === "undefined" || !("caches" in window)) return;
  const names = await caches.keys();
  await Promise.all(names.filter(isUserScopedCache).map((name) => caches.delete(name)));
  const registration = await navigator.serviceWorker?.getRegistration();
  registration?.active?.postMessage({ type: "CLEAR_USER_CACHES" });
}

export function listenForAppUpdate(onReady: (registration: ServiceWorkerRegistration) => void): () => void {
  if (!("serviceWorker" in navigator)) return () => undefined;
  let stop = false;
  void navigator.serviceWorker.getRegistration().then((registration) => {
    if (stop || registration === undefined) return;
    if (registration.waiting && navigator.serviceWorker.controller) onReady(registration);
    registration.addEventListener("updatefound", () => {
      const worker = registration.installing;
      worker?.addEventListener("statechange", () => {
        if (worker.state === "installed" && navigator.serviceWorker.controller) onReady(registration);
      });
    });
  });
  return () => {
    stop = true;
  };
}

/** Tells a waiting worker to take over. Activation reloads every open portal window. */
export function applyAppUpdate(registration: ServiceWorkerRegistration): void {
  if (!shouldApplyUpdate()) return;
  registration.waiting?.postMessage({ type: "SKIP_WAITING" });
}

/** Checks for a new build on a timer, when the tab is shown again, and when the network returns. */
export function watchAppUpdates(registration: ServiceWorkerRegistration): () => void {
  let stop = false;
  const stopListen = listenForAppUpdate((next) => applyAppUpdate(next));
  const check = () => {
    if (stop || document.visibilityState === "hidden") return;
    void registration.update().then(() => {
      if (registration.waiting && navigator.serviceWorker.controller) applyAppUpdate(registration);
    }).catch(() => undefined);
  };
  check();
  document.addEventListener("visibilitychange", check);
  window.addEventListener("focus", check);
  window.addEventListener("online", check);
  const timer = window.setInterval(check, APP_UPDATE_CHECK_MS);
  return () => {
    stop = true;
    stopListen();
    document.removeEventListener("visibilitychange", check);
    window.removeEventListener("focus", check);
    window.removeEventListener("online", check);
    window.clearInterval(timer);
  };
}

export function registerAppWorker(): () => void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return () => undefined;
  if (isPublicNavigation({ hostname: window.location.hostname, pathname: window.location.pathname })) return () => undefined;
  let stopWatch = () => undefined;
  let cancelled = false;
  const register = () => {
    void navigator.serviceWorker
      .register("/sw.js", { scope: "/", updateViaCache: "none" })
      .then((registration) => {
        if (!cancelled) stopWatch = watchAppUpdates(registration);
      })
      .catch(() => undefined);
  };
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register, { once: true });
  return () => {
    cancelled = true;
    stopWatch();
  };
}
