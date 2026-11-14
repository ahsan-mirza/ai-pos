// Fails when a public landing page, canonical, sitemap, robots rule, or nginx redirect drifts.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import {
  SEO_PAGES,
  SITE_ORIGIN,
  canonicalUrl,
  headTags,
  marketingRedirects,
  robotsTxt,
  sitemapXml,
  staticArticle,
} from "../apps/site/src/seo.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const failures = [];

function check(name, ok, detail) {
  if (ok) {
    console.log(`ok  ${name}`);
    return;
  }
  failures.push(`${name}${detail ? `: ${detail}` : ""}`);
  console.log(`FAIL ${name}${detail ? `: ${detail}` : ""}`);
}

const redirects = marketingRedirects();
const indexable = new Map(SEO_PAGES.map((page) => [page.path, page]));
const privatePaths = ["/login", "/signup", "/forgot-password", "/recover-store-code", "/dashboard", "/index.html", "/admin74246/"];

const titles = new Set(SEO_PAGES.map((page) => page.title));
const descriptions = new Set(SEO_PAGES.map((page) => page.description));
check("indexable pages have unique titles", titles.size === SEO_PAGES.length);
check("indexable pages have unique descriptions", descriptions.size === SEO_PAGES.length);

for (const page of SEO_PAGES) {
  const url = canonicalUrl(page);
  check(
    `${page.path} canonical is absolute and self-referencing`,
    url === (page.path === "/" ? `${SITE_ORIGIN}/` : `${SITE_ORIGIN}${page.path}`) &&
      url.startsWith("https://axizpos.com") &&
      !url.includes("?") &&
      !redirects.has(page.path),
  );
  const head = headTags(page, undefined);
  check(`${page.path} title is in the document head`, head.includes(`<title>${page.title.replace(/&/g, "&amp;")}</title>`));
  check(`${page.path} meta description is in the document head`, head.includes('name="description"'));
  check(`${page.path} robots allows indexing`, head.includes('content="index, follow"') && !head.includes("noindex"));
  check(`${page.path} canonical link is in the document head`, head.includes(`rel="canonical" href="${url}"`));
  const article = staticArticle(page);
  check(`${page.path} server HTML contains one H1`, article.includes(`<h1>${page.h1}</h1>`) && article.split("<h1>").length === 2);
  check(`${page.path} image alt text is in the server HTML`, article.includes(`alt="${page.image.alt.replace(/"/g, "&quot;")}"`));
  const jsonMatch = head.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  let graph = [];
  try {
    const parsed = JSON.parse(jsonMatch?.[1] ?? "{}");
    graph = parsed["@graph"] ?? [];
  } catch {
    graph = [];
  }
  const types = graph.map((node) => node["@type"]);
  check(`${page.path} JSON-LD parses`, graph.length > 0 && (jsonMatch?.[1] ?? "").includes('"@context":"https://schema.org"'));
  check(`${page.path} JSON-LD has no ratings, reviews, or a street address`, !/aggregateRating|review|LocalBusiness|streetAddress/i.test(jsonMatch?.[1] ?? ""));
  check(
    `${page.path} JSON-LD types`,
    types.includes("Organization") && types.includes("WebSite") && (page.id === "home" ? types.includes("SoftwareApplication") : types.includes("BreadcrumbList")),
  );
}

const sitemap = sitemapXml();
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
check(
  "sitemap lists only the canonical landing pages",
  locs.length === SEO_PAGES.length && SEO_PAGES.every((page) => locs.includes(canonicalUrl(page))),
);
check("sitemap has no redirected or private URLs", locs.every((loc) => !redirects.has(loc.replace(SITE_ORIGIN, "")) && !loc.includes("?")));

const robots = robotsTxt();
check("robots.txt points at the sitemap", robots.includes(`Sitemap: ${SITE_ORIGIN}/sitemap.xml`));
check("robots.txt does not block the marketing site", robots.includes("Allow: /") && !/Disallow:\s+\/(?:restaurant-pos|grocery-pos|cafe-pos|pricing)?\s*$/m.test(robots));
for (const page of SEO_PAGES) {
  if (page.path === "/") continue;
  check(`robots.txt allows ${page.path}`, !robots.includes(`Disallow: ${page.path}`));
}

const webShell = readFileSync(join(root, "apps/web/index.html"), "utf8");
const consoleShell = readFileSync(join(root, "apps/super-admin/index.html"), "utf8");
check("portal shell stays noindex", webShell.includes('content="noindex, follow"'));
check("console shell stays noindex", consoleShell.includes('content="noindex, nofollow"'));

const nginxFiles = Object.fromEntries(
  ["ai-pos.conf", "ai-pos.https.conf", "ai-pos.apex.conf"].map((name) => [name, readFileSync(join(root, "deploy/nginx", name), "utf8")]),
);
const nginx = Object.values(nginxFiles).join("\n");
check("www HTTPS redirects to the apex", nginxFiles["ai-pos.https.conf"].includes("server_name www.axizpos.com;") && nginxFiles["ai-pos.https.conf"].includes("return 301 https://axizpos.com$request_uri;"));
check("www HTTP stays on HTTP", nginxFiles["ai-pos.conf"].includes("return 301 http://axizpos.com$request_uri;"));
check("port 80 does not force HTTPS", !nginxFiles["ai-pos.conf"].includes("return 301 https://"));
const slugs = SEO_PAGES.filter((page) => page.path !== "/").map((page) => page.path.slice(1));
check(
  "nginx redirects trailing slashes and index.html for every landing page",
  slugs.every((slug) => nginx.includes(slug)) && nginx.includes("/index\\.html$") && nginx.includes("return 301 $scheme://axizpos.com/$1$is_args$args;"),
);
for (const section of ["solutions", "features", "industries", "pricing", "contact"]) {
  check(`nginx redirects /${section}`, nginx.includes(section) && nginx.includes("return 301 $scheme://axizpos.com/#$1;"));
}
for (const [source, target] of [
  ["/supermarket-pos", "/grocery-pos"],
  ["/ai", "/#intelligence"],
  ["/copilot", "/#intelligence"],
]) {
  check(`nginx redirects ${source}`, nginx.includes(`location = ${source}`) && nginx.includes(`return 301 $scheme://axizpos.com${target};`));
}
for (const missing of ["/blog", "/home"]) {
  check(`nginx returns 404 for ${missing}`, nginx.includes(`location = ${missing} { return 404; }`));
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const path = join(dir, entry);
    if (statSync(path).isDirectory()) walk(path, files);
    else if (/\.(tsx|ts)$/.test(entry) && entry !== "seo.ts") files.push(path);
  }
  return files;
}

const hrefs = [];
for (const file of walk(join(root, "apps/site/src"))) {
  const source = readFileSync(file, "utf8");
  for (const match of source.matchAll(/"(\/[a-z0-9][^"]*)"/g)) {
    hrefs.push({ file: relative(root, file), href: match[1] });
  }
}
for (const { file, href } of hrefs) {
  const path = href.split("#")[0] || "/";
  const hashOnly = href.startsWith("/#");
  const known =
    hashOnly ||
    indexable.has(path) ||
    privatePaths.some((item) => path === item || path.startsWith(item)) ||
    href.startsWith("/brand/") ||
    href.startsWith("/pos/") ||
    href.startsWith("/portal/");
  check(`${file} link ${href} is not a redirect`, !redirects.has(path) && !redirects.has(href));
  check(`${file} link ${href} resolves`, known);
}

const home = readFileSync(join(root, "apps/site/index.html"), "utf8");
check("marketing HTML sets a mobile viewport", home.includes('name="viewport"'));

if (failures.length > 0) {
  console.error(`\n${failures.length} SEO check${failures.length === 1 ? "" : "s"} failed.`);
  process.exit(1);
}
console.log("\nSEO checks passed.");
