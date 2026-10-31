import { isUserScopedCache } from "./cachePolicy";

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

let reloading = false;

/** Activates the waiting worker, then reloads once. Never called on its own. */
export function applyAppUpdate(registration: ServiceWorkerRegistration): void {
  if (reloading) return;
  const waiting = registration.waiting;
  if (waiting === null) {
    window.location.reload();
    return;
  }
  reloading = true;
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    window.location.reload();
  });
  waiting.postMessage({ type: "SKIP_WAITING" });
}

export function registerAppWorker(): void {
  if (!import.meta.env.PROD || !("serviceWorker" in navigator)) return;
  const register = () => {
    void navigator.serviceWorker.register("/sw.js", { scope: "/" });
  };
  if (document.readyState === "complete") register();
  else window.addEventListener("load", register);
}
