/// <reference lib="webworker" />
import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";
import { registerRoute, setCatchHandler } from "workbox-routing";
import { NetworkOnly } from "workbox-strategies";
import { isUserScopedCache, mayCacheRequest } from "../src/pwa/cachePolicy";

declare const self: ServiceWorkerGlobalScope;

// The app shell only. API and media responses are never written here.
precacheAndRoute(self.__WB_MANIFEST, {
  navigateFallback: "/index.html",
  navigateFallbackDenylist: [/^\/api(?:\/|$)/, /^\/media(?:\/|$)/],
});
cleanupOutdatedCaches();

registerRoute(({ url, request }) => !mayCacheRequest(url.pathname, request.headers.has("authorization")), new NetworkOnly());

setCatchHandler(async ({ request }) => {
  if (request.mode === "navigate") {
    const page = await caches.match("/offline.html");
    if (page) return page;
  }
  return Response.error();
});

self.addEventListener("message", (event) => {
  const data = event.data as { type?: string } | undefined;
  if (data?.type === "SKIP_WAITING") self.skipWaiting();
  if (data?.type === "CLEAR_USER_CACHES") {
    event.waitUntil(
      caches.keys().then((names) => Promise.all(names.filter(isUserScopedCache).map((name) => caches.delete(name)))),
    );
  }
});

self.addEventListener("activate", (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
  let title = "Business Pro";
  let body = "";
  let url = "/";
  try {
    const data = event.data?.json() as { title?: string; body?: string; url?: string } | undefined;
    title = data?.title || title;
    body = data?.body || "";
    if (data?.url?.startsWith("/")) url = data.url;
  } catch {
    body = event.data?.text() ?? "";
  }
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/icons/icon-192.png",
      badge: "/icons/favicon-32.png",
      data: { url },
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const raw = (event.notification.data as { url?: string } | undefined)?.url ?? "/";
  const target = new URL(raw.startsWith("/") ? raw : "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((openClients) => {
      const existing = openClients.find((client) => client.url.startsWith(self.location.origin));
      if (existing) return existing.focus();
      return self.clients.openWindow(target);
    }),
  );
});
