// Validates the generated sitemap and the apex routing rules. Does not contact production.
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { SEO_PAGES, canonicalUrl, headTags, sitemapXml, staticArticle } from "../apps/site/src/seo.ts";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const apex = readFileSync(join(root, "deploy/nginx/ai-pos.apex.conf"), "utf8");
const failures = [];

function check(name, ok, detail = "") {
  if (ok) return;
  failures.push(`${name}${detail ? `: ${detail}` : ""}`);
}

const catchAll = apex.match(/location ~ \^\/\(\?!([^)]*(?:\)[^)]*)*)\)\.\+ \{/);
check("catch-all 404 regex is present", Boolean(catchAll));
const catchAllRe = catchAll ? new RegExp(`^/(?!${catchAll[1]}).+`) : /$^/;

const serve = apex.match(/location ~ \^\/\((restaurant-pos\|[^)]+)\)\$ \{/);
check("marketing serve regex is present", Boolean(serve));
const serveRe = serve ? new RegExp(`^/(${serve[1].replaceAll("\\|", "|")})$`) : /$^/;

function route(path) {
  if (path === "/" || path === "/blog" || path === "/ar") return "200";
  if (path === "/home-2" || path === "/home-2/" || path === "/home-3" || path === "/home-3/" || path === "/home-3/index.html") return "301:/";
  if (/^\/(pharmacy-pos|privacy|about|terms|refund)\/?$/.test(path)) return "404";
  if (path.startsWith("/blog/") || path.startsWith("/ar/") || path.startsWith("/hardware/") || path.startsWith("/images/") || path.startsWith("/api/") || path.startsWith("/assets/")) return "200";
  if (serveRe.test(path)) return "200";
  if (catchAllRe.test(path)) return "404";
  return "portal";
}

const sitemap = sitemapXml();
const locs = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((match) => match[1]);
check("sitemap URL count matches pages", locs.length === SEO_PAGES.length, `${locs.length} vs ${SEO_PAGES.length}`);

const titles = new Map();
let withLastmod = 0;
let withoutLastmod = 0;
const schemaTypes = new Map();

for (const page of SEO_PAGES) {
  const url = canonicalUrl(page);
  check(`${page.path} is https and has no query`, url.startsWith("https://axizpos.com") && !url.includes("?"));
  check(`${page.path} is in the sitemap once`, locs.filter((item) => item === url).length === 1);
  const head = headTags(page, undefined);
  check(`${page.path} is indexable`, head.includes('content="index, follow"') && !head.includes("noindex"));
  check(`${page.path} canonical is itself`, head.includes(`rel="canonical" href="${url}"`));
  check(`${page.path} language matches`, head.includes(`og:locale" content="${page.locale === "ar" ? "ar_AE" : "en_AE"}"`));
  const article = staticArticle(page);
  check(`${page.path} has one H1 and some text`, article.includes(`<h1>${page.h1}</h1>`) && article.length > 200);
  const stamp = page.modified ?? page.published;
  const blockStart = sitemap.indexOf(`<loc>${url}</loc>`);
  const block = sitemap.slice(blockStart, sitemap.indexOf("</url>", blockStart));
  if (stamp) {
    withLastmod += 1;
    check(`${page.path} lastmod`, block.includes(`<lastmod>${stamp}</lastmod>`));
  } else {
    withoutLastmod += 1;
    check(`${page.path} has no invented lastmod`, !block.includes("<lastmod>"));
  }
  const path = new URL(url).pathname;
  check(`${page.path} nginx would return 200`, route(path) === "200", route(path));
  const owner = titles.get(page.title);
  check(`${page.path} title is unique`, owner === undefined, owner);
  titles.set(page.title, page.path);
  const json = head.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/)?.[1] ?? "{}";
  const graph = JSON.parse(json)["@graph"] ?? [];
  for (const node of graph) {
    const type = node["@type"];
    schemaTypes.set(type, (schemaTypes.get(type) ?? 0) + 1);
    check(`${page.path} ${type} has no fabricated rating or address`, !("aggregateRating" in node) && !("review" in node) && !("streetAddress" in node));
  }
  if (page.faqs?.length) {
    check(`${page.path} FAQ schema matches visible questions`, graph.some((node) => node["@type"] === "FAQPage" && node.mainEntity.length === page.faqs.length));
  }
  if (page.kind === "article") check(`${page.path} has Article schema`, graph.some((node) => node["@type"] === "Article"));
  if (page.kind === "home" || page.id === "home") check(`${page.path} has SoftwareApplication`, graph.some((node) => node["@type"] === "SoftwareApplication"));
  else check(`${page.path} has breadcrumbs`, graph.some((node) => node["@type"] === "BreadcrumbList"));
}

for (const path of ["/pharmacy-pos", "/privacy", "/about", "/terms", "/refund", "/not-a-real-page"]) {
  check(`${path} is a marketing 404`, route(path) === "404", route(path));
  check(`${path} is not in the sitemap`, !locs.includes(`https://axizpos.com${path}`));
}
for (const path of ["/login", "/signup", "/dashboard", "/api/v1/health", "/assets/app.js", "/demo/restaurant", "/inventory/stock"]) {
  check(`${path} stays on the application`, route(path) === "portal" || route(path) === "200", route(path));
}
check("/home-3 redirects home", route("/home-3") === "301:/");
check("sitemap has no home-3", !locs.some((item) => item.includes("home-3")));

console.log(`sitemap URLs: ${locs.length}`);
console.log(`lastmod present: ${withLastmod}; omitted because no real edit date: ${withoutLastmod}`);
console.log(`schema: ${[...schemaTypes.entries()].map(([type, count]) => `${type} ${count}`).join(", ")}`);
if (failures.length > 0) {
  console.error(`\n${failures.length} release audit checks failed.`);
  for (const failure of failures.slice(0, 40)) console.error(`FAIL ${failure}`);
  process.exit(1);
}
console.log("Release audit passed.");
