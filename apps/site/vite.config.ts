import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv, type Plugin } from "vite";
import { SEO_PAGES, headTags, marketingRedirects, notFoundHtml, robotsTxt, sitemapXml, seoPage, staticArticle } from "./src/seo";

const root = fileURLToPath(new URL(".", import.meta.url));

function siteSeo(): Plugin {
  const entries = Object.fromEntries(
    SEO_PAGES.map((page) => [page.id, resolve(root, page.path === "/" ? "index.html" : `${page.path.slice(1)}/index.html`)]),
  );
  let verification: string | undefined;
  let measurementId: string | undefined;
  const rewritePage = (url: string | undefined): string | undefined => {
    const path = url?.split("?")[0];
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
      return { build: { rollupOptions: { input: entries } } };
    },
    transformIndexHtml: {
      order: "pre",
      handler(html) {
        if (!html.includes("<!-- site-seo -->")) return html;
        const id = html.match(/data-page="([^"]+)"/)?.[1] ?? "home";
        const page = seoPage(id);
        if (!page) return html;
        const tags = headTags(page, verification, measurementId);
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
});
