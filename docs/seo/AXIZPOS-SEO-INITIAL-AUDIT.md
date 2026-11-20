# AxizPOS technical SEO audit

Inspected on 20 November 2026. Production was not modified. The source of truth is this repository. Live HTTP checks used `https://axizpos.com` and are recorded separately from source behaviour.

## Stack

| Item | Finding |
| --- | --- |
| Marketing site | `apps/site`. Vite 6.3 and React 19. Not Next.js. There is no App Router or Pages Router. |
| Rendering | Multi-page build. `apps/site/src/seo.ts` writes a title, description, one canonical, robots, Open Graph, Twitter, JSON-LD, and an article into each `index.html`. React then runs in `#root`. |
| Portal | `apps/web`. Client-rendered SPA. Anonymous HTML is the shell in `apps/web/index.html`. |
| Console | `apps/super-admin`. Served at `/admin74246/`. |
| Preferred origin | `https://axizpos.com`, constant `SITE_ORIGIN` in `apps/site/src/seo-types.ts`. |
| Edge | `deploy/nginx/ai-pos.apex.conf` serves marketing files and proxies application routes. `www.axizpos.com` 301s to the apex in `deploy/nginx/ai-pos.https.conf`. |

## Live checks, 20 November 2026

| URL | Status | Robots meta | X-Robots-Tag | Canonical |
| --- | --- | --- | --- | --- |
| `https://axizpos.com/` | 200 | `index, follow` | absent | `https://axizpos.com/` |
| `https://www.axizpos.com/` | 301 | n/a | absent | Location `https://axizpos.com/` |
| `http://axizpos.com/` | 200 | `index, follow` | absent | `https://axizpos.com/` |
| `/cafe-pos`, `/restaurant-pos`, `/grocery-pos`, `/electronics-pos`, `/fashion-pos`, `/wholesale-pos`, `/quick-service-pos` | 200 | `index, follow` | absent | self on `https://axizpos.com` |
| `/cafe-pos/` | 301 | n/a | absent | `https://axizpos.com/cafe-pos` |
| `/cafe-pos?utm_source=test` | 200 | `index, follow` | absent | `https://axizpos.com/cafe-pos` |
| `/retail-pos`, `/pos-software-uae`, `/offline-pos`, `/ai-pos`, `/blog`, `/explore`, `/hardware`, `/ar` | 200 | `index, follow` | absent | self |
| `/pricing` | 301 | n/a | absent | `https://axizpos.com/#pricing` |
| `/home-3` | 301 | n/a | absent | `https://axizpos.com/` |
| `/pharmacy-pos`, `/privacy`, `/about` | 404 | `noindex` | absent on the live response | none |
| `/hardware/products/not-a-real-product` | 200 | `index, follow` | absent | `https://axizpos.com/hardware` in the HTML |
| `/login`, `/signup`, `/dashboard`, `/inventory` | 200 | `noindex, follow` | absent | none |
| `/admin74246/` | 200 | `noindex, nofollow` | absent | none |
| `/robots.txt` | 200 | n/a | absent | n/a |
| `/sitemap.xml` | 200 | n/a | absent | 107 `<loc>` values |

Homepage title in the response: `AxizPOS | AI-Powered POS for Retail and Restaurants`. H1: `Run Your Business Better with AxizPOS`.

One sample from this network, not a Core Web Vitals report: homepage time to first byte 0.358s, `/cafe-pos` 0.148s.

## What is already in place

- Public pages are the `SEO_PAGES` list. Source sitemap length is 107, the same count as the live sitemap on this date.
- Each public page gets one self-referencing `https://axizpos.com` canonical and `index, follow`.
- Private portal HTML uses `noindex, follow`. The console uses `noindex, nofollow`.
- Unpublished paths such as `/pharmacy-pos`, `/privacy`, and `/about` are a marketing 404 with `noindex`, not a portal shell.
- Trailing slashes on landing pages 301 to the slashless path.
- `robots.txt` allows `/`, points at `https://axizpos.com/sitemap.xml`, and disallows `/api/`, `/admin74246/`, `/login`, `/signup`, `/forgot-password`, `/recover-store-code`, and `/dashboard`.
- JSON-LD in source is Organization, WebSite, SoftwareApplication on the home page, BreadcrumbList, FAQPage where the page has questions, and Article on guides. The SEO check rejects ratings, reviews, and a street address.
- `scripts/seo-check.mjs` fails the build when a public page, sitemap, robots rule, or nginx redirect drifts.

## Defects and limits

1. The two Search Console URLs are not in the repository. No export, CSV, or inspection file names them. They are not guessed in this audit.
2. `http://axizpos.com/` returns 200 with the same indexable HTML. The canonical is HTTPS. Port 80 is intentionally left serving content in `deploy/nginx/ai-pos.conf` so a later HTTPS redirect can be applied separately. This audit does not flip that.
3. `/hardware/products/...` is the hardware document for every slug. The HTML canonical is `/hardware`. Before this change, the browser rewrote that canonical to the product path after the catalogue loaded. That second URL is not in the sitemap and is not in the first HTML.
4. The live 404 for `/pharmacy-pos` has a `noindex` meta tag and no `X-Robots-Tag`. Source nginx now sets that header on the internal 404 document. The live edge does not have that header until the nginx config is deployed.
5. `robots.txt` disallows several HTML routes that also send `noindex`. Google cannot see a `noindex` tag on a URL it is told not to crawl. Those disallow lines were left as they are until the Search Console URLs are classified.
6. Anonymous portal HTML does not include customer records. It is a 2 KB shell. Access control still runs after JavaScript in `apps/web`. `noindex` is not the access control.
7. Field Core Web Vitals were not measured. No Lighthouse or CrUX export was available.

## Indexing is not claimed

A 200 response, a sitemap entry, and a code change do not mean Google has indexed a URL. Search Console was not opened for this audit.
