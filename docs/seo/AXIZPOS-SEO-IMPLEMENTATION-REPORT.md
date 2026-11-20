# SEO implementation report

Date: 20 November 2026. Production was not edited and was not deployed. Google has not been asked to recrawl anything. Search Console indexing is not claimed.

## Original Search Console rows

| Issue | URL | Status |
| --- | --- | --- |
| Excluded by `noindex` | Not supplied | `AWAITING GSC URL` |
| Discovered — currently not indexed | Not supplied | `AWAITING GSC URL` |

Indexing for those unknown URLs was not changed.

## What changed in source

| Change | Why |
| --- | --- |
| `apps/site/src/indexability.ts` | One classification for public, private, redirect, duplicate, and unpublished paths. `robots.txt` disallow lines come from that list, and the lines themselves are unchanged. |
| `apps/site/src/indexability.test.ts` | Fails if a private prefix or a redirect enters the sitemap, or if a public page emits `noindex` or a second canonical. |
| `apps/site/src/hardware/HardwarePage.tsx` | Stops replacing the `/hardware` canonical with `/hardware/products/{slug}`, and stops adding a second Product JSON-LD document. The catalogue page remains the indexable URL. |
| `deploy/nginx/ai-pos.apex.conf` | The internal marketing 404 sends `X-Robots-Tag: noindex`. The HTML already had the meta tag. Live responses on this date did not send the header. |
| `scripts/seo-check.mjs` | Checks that 404 header and ignores the policy file when it scans marketing links. |

`node scripts/seo-check.mjs` passed. `pnpm --filter @ai-pos/site exec vitest run src/indexability.test.ts` passed, 5 tests.

## Before and after

| Surface | Before | After this source change | Live on 20 November 2026 |
| --- | --- | --- | --- |
| Public canonical | One `https://axizpos.com` canonical | Unchanged | Sampled pages matched |
| Public robots | `index, follow` | Unchanged | Sampled pages matched |
| Hardware product canonical | HTML said `/hardware`. JavaScript replaced it with the product URL. | JavaScript leaves the HTML canonical | Live HTML still says `/hardware` until deploy. The old script is still on the server. |
| Marketing 404 | Meta `noindex`. Nginx `add_header` on the redirecting location was not visible on the live 404. | `X-Robots-Tag: noindex` on `location = /404.html` | Meta `noindex` only. Header absent. |
| Sitemap | 107 public URLs | Still those 107 | Live file also had 107 `<loc>` values |
| `robots.txt` | Allow `/`, sitemap line, seven disallow lines | Same text | Same text |
| Portal | `noindex, follow` shell | Unchanged | `/login` returned that shell |
| HTTP to HTTPS | Port 80 returns 200 | Unchanged on purpose | `http://axizpos.com/` returned 200 |

## Route classification

See `AXIZPOS-ROUTE-INDEXABILITY-MATRIX.md`. Public marketing pages stay eligible for indexing. Login, the business portal, the console, and the API stay out of the sitemap. `/pharmacy-pos`, `/privacy`, and `/about` stay unpublished.

## Content and structured data

The sampled industry pages already have distinct titles, descriptions, and H1s, and the source articles describe the presets that exist in the product. Copy was not rewritten. No testimonials, ratings, certifications, or customer counts were added. Existing JSON-LD was left in place. The hardware page no longer injects a Product graph onto a URL whose canonical is the catalogue.

## Performance

One request from this network: homepage time to first byte 0.358s, `/cafe-pos` 0.148s. That is not a Core Web Vitals result. Field and lab Core Web Vitals were `NOT RUN`.

## Security

`/login` anonymous HTML was the Business Pro shell. It did not contain an email, token, password, or customer record. Portal route guards in `apps/web` were not removed. `robots.txt` was not treated as access control.

## Status

| Item | Status |
| --- | --- |
| Unknown `noindex` URL | `AWAITING GSC URL` |
| Unknown discovered URL | `AWAITING GSC URL` |
| Public pages eligible in HTML and sitemap | `FIXED` in the existing source. Live samples matched. |
| Private portal and console | `INTENTIONALLY EXCLUDED` |
| Unpublished `/pharmacy-pos`, `/privacy`, `/about` | `INTENTIONALLY EXCLUDED` |
| Hardware product URLs as separate canonicals | `FIXED` in source. Not deployed. |
| 404 `X-Robots-Tag` | `FIXED` in source. Not deployed. |
| Port 80 still serving the site | `BLOCKED` by the existing port 80 policy. Not changed. |
| `robots.txt` disallow on HTML routes that also use `noindex` | `INTENTIONALLY EXCLUDED` until the Search Console URLs are classified. |
| Core Web Vitals | `NOT RUN` |
| Google indexing of any URL | `NOT RUN` |
