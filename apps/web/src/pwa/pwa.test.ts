import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isUserScopedCache, mayCacheRequest } from "./cachePolicy";
import { bannerVisible, installSurface, isIos, isStandalone, menuAction, shouldApplyUpdate } from "./install";
import { PWA_ICONS, pwaManifest } from "./manifest";
import { pushConfigured } from "./push";

describe("Business Pro PWA", () => {
  it("publishes a valid install identity", () => {
    expect(pwaManifest.name).toBe("AxizPOS Business Pro");
    expect(pwaManifest.short_name).toBe("Business Pro");
    expect(pwaManifest.description).toContain("AxizPOS Business Pro");
    expect(pwaManifest.start_url).toBe("/");
    expect(pwaManifest.scope).toBe("/");
    expect(pwaManifest.display).toBe("standalone");
    expect(pwaManifest.orientation).toBe("any");
    expect(pwaManifest.theme_color).toBe("#f26a21");
    expect(pwaManifest.background_color).toBe("#eaeaea");
    expect(pwaManifest.icons.map((icon) => icon.sizes)).toEqual(["192x192", "512x512", "192x192", "512x512"]);
    expect(pwaManifest.icons.map((icon) => icon.purpose)).toEqual(["any", "any", "maskable", "maskable"]);
    expect(pwaManifest.shortcuts[0]?.url).toBe("/");
  });

  it("ships the icon files the manifest names", () => {
    const dir = join(process.cwd(), "public", "icons");
    for (const file of PWA_ICONS) expect(existsSync(join(dir, file)), file).toBe(true);
    for (const icon of pwaManifest.icons) {
      expect(existsSync(join(process.cwd(), "public", icon.src.replace(/^\//, "")))).toBe(true);
    }
  });

  it("offers Chromium install, iOS steps, or nothing", () => {
    expect(isIos("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)")).toBe(true);
    expect(isIos("Mozilla/5.0 (Macintosh)", 5, "MacIntel")).toBe(true);
    expect(isIos("Mozilla/5.0 (Windows NT 10.0)")).toBe(false);
    expect(isStandalone("standalone")).toBe(true);
    expect(isStandalone("browser", true)).toBe(true);
    expect(installSurface({ standalone: true, ios: true, canPrompt: true })).toBe("installed");
    expect(installSurface({ standalone: false, ios: false, canPrompt: true })).toBe("prompt");
    expect(installSurface({ standalone: false, ios: true, canPrompt: false })).toBe("ios");
    expect(installSurface({ standalone: false, ios: false, canPrompt: false })).toBe("hidden");
    expect(menuAction("prompt")).toBe("install");
    expect(menuAction("ios")).toBe("ios");
    expect(menuAction("installed")).toBeNull();
    expect(menuAction("hidden")).toBeNull();
    expect(bannerVisible("prompt", false)).toBe(true);
    expect(bannerVisible("ios", false)).toBe(true);
    expect(bannerVisible("prompt", true)).toBe(false);
    expect(bannerVisible("installed", false)).toBe(false);
  });

  it("keeps API, media, and authorized responses out of the cache", () => {
    expect(mayCacheRequest("/assets/index-abc.js", false)).toBe(true);
    expect(mayCacheRequest("/index.html", false)).toBe(true);
    expect(mayCacheRequest("/api/v1/sales", false)).toBe(false);
    expect(mayCacheRequest("/api/v1/auth/login", false)).toBe(false);
    expect(mayCacheRequest("/media/tenant/products/a.webp", false)).toBe(false);
    expect(mayCacheRequest("/icons/icon-192.png", true)).toBe(false);
    expect(isUserScopedCache("business-pro-user")).toBe(true);
    expect(isUserScopedCache("workbox-precache-v2")).toBe(false);
    expect(isUserScopedCache("api-responses")).toBe(true);
  });

  it("serves the shell offline and leaves live data on the network", () => {
    const worker = readFileSync(join(process.cwd(), "service-worker", "sw.ts"), "utf8");
    expect(worker).toContain('navigateFallback: "/index.html"');
    expect(worker).toContain("NetworkOnly");
    expect(worker).toContain('caches.match("/offline.html")');
    expect(worker).toContain('if (data?.type === "SKIP_WAITING") self.skipWaiting()');
    expect(worker).toContain('addEventListener("push"');
    expect(worker).toContain('addEventListener("notificationclick"');
    expect(worker).not.toContain("requestPermission");
    expect(worker).not.toContain('addEventListener("install"');
    const auth = readFileSync(join(process.cwd(), "src", "lib", "auth.tsx"), "utf8");
    expect(auth).toContain("clearUserCaches");
    expect(auth).toContain("sessionStorage");
    expect(auth).not.toContain("localStorage.setItem(STORAGE_KEY");
    const registration = readFileSync(join(process.cwd(), "src", "pwa", "register.ts"), "utf8");
    expect(registration).toContain('register("/sw.js", { scope: "/" })');
    expect(registration).toContain("import.meta.env.PROD");
    expect(registration).not.toContain("localStorage");
  });

  it("updates only when the person confirms, and does not ask for push", () => {
    expect(shouldApplyUpdate(false)).toBe(false);
    expect(shouldApplyUpdate(true)).toBe(true);
    expect(pushConfigured()).toBe(false);
  });
});
