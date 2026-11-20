import { describe, expect, it } from "vitest";
import {
  CONSOLIDATED_REDIRECTS,
  INDEXABILITY,
  PRIVATE_HTML_PREFIXES,
  ROBOTS_DISALLOW,
  classifyPath,
  isPrivatePath,
  normalizePath,
} from "./indexability";
import { SEO_PAGES, canonicalUrl, headTags, robotsTxt, sitemapXml } from "./seo";

const publicPaths = new Set(SEO_PAGES.map((page) => page.path));

describe("route indexability", () => {
  it("indexes only the declared public pages", () => {
    for (const page of SEO_PAGES) {
      expect(classifyPath(page.path, publicPaths)).toBe(INDEXABILITY.public);
      expect(isPrivatePath(page.path)).toBe(false);
    }
  });

  it("keeps private, unpublished, and redirected paths out of the public set", () => {
    expect(classifyPath("/login", publicPaths)).toBe(INDEXABILITY.private);
    expect(classifyPath("/dashboard/sales", publicPaths)).toBe(INDEXABILITY.private);
    expect(classifyPath("/admin74246/", publicPaths)).toBe(INDEXABILITY.private);
    expect(classifyPath("/pharmacy-pos", publicPaths)).toBe(INDEXABILITY.invalid);
    expect(classifyPath("/privacy", publicPaths)).toBe(INDEXABILITY.invalid);
    expect(classifyPath("/home-3", publicPaths)).toBe(INDEXABILITY.redirect);
    expect(classifyPath("/supermarket-pos", publicPaths)).toBe(INDEXABILITY.redirect);
    expect(classifyPath("/hardware/products/ax-15", publicPaths)).toBe(INDEXABILITY.duplicate);
    expect(classifyPath("/cafe-pos?utm_source=ad", publicPaths)).toBe(INDEXABILITY.duplicate);
  });

  it("puts only canonical public URLs in the sitemap", () => {
    const locs = [...sitemapXml().matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
    expect(new Set(locs).size).toBe(locs.length);
    expect(locs).toHaveLength(SEO_PAGES.length);
    for (const loc of locs) {
      expect(loc?.startsWith("https://axizpos.com")).toBe(true);
      const path = loc === "https://axizpos.com/" ? "/" : loc!.replace("https://axizpos.com", "");
      expect(classifyPath(path, publicPaths)).toBe(INDEXABILITY.public);
      expect(path in CONSOLIDATED_REDIRECTS).toBe(false);
      for (const prefix of PRIVATE_HTML_PREFIXES) {
        expect(path === prefix || path.startsWith(`${prefix}/`)).toBe(false);
      }
    }
  });

  it("does not mark a public page noindex, and does not disallow it", () => {
    const robots = robotsTxt();
    expect(robots).toContain("Sitemap: https://axizpos.com/sitemap.xml");
    expect(robots).toContain("Allow: /");
    for (const path of ROBOTS_DISALLOW) {
      expect(robots).toContain(`Disallow: ${path}`);
    }
    for (const page of SEO_PAGES) {
      const head = headTags(page, undefined);
      const canonicals = head.match(/rel="canonical"/g) ?? [];
      expect(canonicals).toHaveLength(1);
      expect(head).toContain(`href="${canonicalUrl(page)}"`);
      expect(head).toContain('content="index, follow"');
      expect(head).not.toContain("noindex");
      expect(robots.split(/\r?\n/).includes(`Disallow: ${page.path}`)).toBe(false);
    }
  });

  it("treats a trailing slash on a public page as a redirect, not a second URL", () => {
    expect(normalizePath("/cafe-pos/")).toBe("/cafe-pos");
    expect(classifyPath("/cafe-pos/", publicPaths)).toBe(INDEXABILITY.redirect);
  });
});
