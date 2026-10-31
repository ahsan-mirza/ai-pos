/// <reference lib="webworker" />
import { cleanupOutdatedCaches, createHandlerBoundToURL, precacheAndRoute } from "workbox-precaching";
import { registerRoute, setCatchHandler } from "workbox-routing";
import { NetworkOnly } from "workbox-strategies";
import { isPortalNavigation, isUserScopedCache, mayCacheRequest } from "../src/pwa/cachePolicy";

declare const self: ServiceWorkerGlobalScope;

// Registered before the precache so a marketing navigation, including /index.html, is never the portal shell.
registerRoute(
  ({ request, url }) => request.mode === "navigate" && !isPortalNavigation(url),
  new NetworkOnly(),
);

// Portal shell only. Marketing pages, API responses, and media are not in this precache.
precacheAndRoute(self.__WB_MANIFEST);
cleanupOutdatedCaches();

const portalShell = createHandlerBoundToURL("/index.html");

registerRoute(
  ({ request, url }) => request.mode === "navigate" && isPortalNavigation(url),
  portalShell,
);

registerRoute(
  ({ request, url }) =>
    request.mode !== "navigate" && !mayCacheRequest(url.pathname, request.headers.has("authorization"), url.hostname),
  new NetworkOnly(),
);

setCatchHandler(async ({ request, url }) => {
  if (request.mode === "navigate" && isPortalNavigation(url)) {
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
  let url = "/dashboard";
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
  const raw = (event.notification.data as { url?: string } | undefined)?.url ?? "/dashboard";
  const target = new URL(raw.startsWith("/") ? raw : "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((openClients) => {
      const existing = openClients.find((client) => client.url.startsWith(self.location.origin));
      if (existing) return existing.focus();
      return self.clients.openWindow(target);
    }),
  );
});
