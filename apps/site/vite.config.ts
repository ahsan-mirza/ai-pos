import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import { SEO_PAGES, headTags, marketingRedirects, measurementSnippet, notFoundHtml, publicWorkerBoot, robotsTxt, sitemapXml, seoPage, staticArticle } from "./src/seo";
import { staticHeroHtml } from "./src/staticHero";

const root = fileURLToPath(new URL(".", import.meta.url));

function siteSeo(): Plugin {
  const entries = Object.fromEntries(
    SEO_PAGES.map((page) => [page.id, resolve(root, page.path === "/" ? "index.html" : `${page.path.slice(1)}/index.html`)]),
  );
  entries["home-2"] = resolve(root, "home-2/index.html");
  entries["home-3"] = resolve(root, "home-3/index.html");
  let verification: string | undefined;
  let measurementId: string | undefined;
  let bingVerification: string | undefined;
  const previewPath = (url: string | undefined): string | undefined => {
    const path = url?.split("?")[0];
    if (path !== "/home-2" && path !== "/home-3") return undefined;
    const query = url?.includes("?") ? url.slice(url.indexOf("?")) : "";
    return `${path}/index.html${query}`;
  };
  const rewritePage = (url: string | undefined): string | undefined => {
    const preview = previewPath(url);
    if (preview) return preview;
    const path = url?.split("?")[0];
    if (path === "/hardware" || (path?.startsWith("/hardware/") && !path.includes("."))) {
      const query = url?.includes("?") ? url.slice(url.indexOf("?")) : "";
      return `/hardware/index.html${query}`;
    }
    if (!path || !SEO_PAGES.some((page) => page.path === path)) return undefined;
    const query = url?.includes("?") ? url.slice(url.indexOf("?")) : "";
    return `${path}/index.html${query}`;
  };
  const crawlFile = (path: string | undefined): { body: string; type: string } | undefined => {
    if (path === "/sitemap.xml") return { body: sitemapXml(), type: "application/xml" };
    if (path === "/robots.txt") return { body: robotsTxt(), type: "text/plain" };
    return undefined;
  };

  return {
    name: "site-seo",
    config(_config, { mode }) {
      const env = loadEnv(mode, resolve(root, "../.."), "VITE_");
      verification = env.VITE_GOOGLE_SITE_VERIFICATION;
      measurementId = env.VITE_GA_MEASUREMENT_ID;
      bingVerification = env.VITE_BING_SITE_VERIFICATION;
      return { build: { rollupOptions: { input: entries } } };
    },
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        if (!html.includes("/fonts/archivo-latin.woff2")) {
          const priority = html.includes("/src/home2/") ? "low" : "high";
          html = html.replace(
            "</head>",
            `    <link rel="preload" href="/fonts/archivo-latin.woff2" as="font" type="font/woff2" crossorigin fetchpriority="${priority}" />\n  </head>`,
          );
        }
        if (html.includes("/src/home2/") && !html.includes('id="h2-static-hero"')) {
          html = html.replace('<div id="root">', `${staticHeroHtml()}\n    <div id="root">`);
        }
        if (!html.includes("article[data-seo-static]")) {
          html = html.replace(
            "</head>",
            `    <script>document.documentElement.classList.add("js")</script>\n    <style>html.js #root>article[data-seo-static]{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}</style>\n  </head>`,
          );
        }
        if (html.includes('data-page="home-3"')) {
          const extra = [measurementSnippet(measurementId), publicWorkerBoot()].filter(Boolean).join("\n    ");
          html = html.replace("</head>", `    ${extra}\n  </head>`);
        }
        if (!html.includes("<!-- site-seo -->")) return html;
        const id = html.match(/data-page="([^"]+)"/)?.[1] ?? "home";
        const page = seoPage(id);
        if (!page) return html;
        const tags = headTags(page, verification, measurementId, bingVerification);
        return html
          .replace("<!-- site-seo -->", tags)
          .replace('<div id="root"></div>', `<div id="root">${staticArticle(page)}</div>`);
      },
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split("?")[0];
        const target = path ? marketingRedirects().get(path) : undefined;
        if (target) {
          res.statusCode = 301;
          res.setHeader("Location", target);
          res.end();
          return;
        }
        const rewritten = rewritePage(req.url);
        if (rewritten) req.url = rewritten;
        const served = crawlFile(req.url?.split("?")[0]);
        if (!served) return next();
        res.setHeader("Content-Type", served.type);
        res.end(served.body);
      });
    },
    configurePreviewServer(server) {
      server.middlewares.use((req, res, next) => {
        const path = req.url?.split("?")[0];
        const target = path ? marketingRedirects().get(path) : undefined;
        if (target) {
          res.statusCode = 301;
          res.setHeader("Location", target);
          res.end();
          return;
        }
        const rewritten = rewritePage(req.url);
        if (rewritten) req.url = rewritten;
        const served = crawlFile(req.url?.split("?")[0]);
        if (!served) return next();
        res.setHeader("Content-Type", served.type);
        res.end(served.body);
      });
    },
    generateBundle() {
      this.emitFile({ type: "asset", fileName: "sitemap.xml", source: sitemapXml() });
      this.emitFile({ type: "asset", fileName: "robots.txt", source: robotsTxt() });
      this.emitFile({ type: "asset", fileName: "404.html", source: notFoundHtml() });
    },
  };
}

export default defineConfig({
  envDir: "../../",
  plugins: [siteSeo(), react()],
  resolve: { dedupe: ["react", "react-dom"] },
  appType: "mpa",
  server: { port: 5175, strictPort: true },
  build: { assetsDir: "site-assets" },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
