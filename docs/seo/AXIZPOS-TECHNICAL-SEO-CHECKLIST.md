# Technical SEO checklist

Checked on 20 November 2026 against `https://axizpos.com` and against the marketing source. "Indexed" is filled only from Search Console. That column is not verified.

| Check | Result |
| --- | --- |
| Public industry URLs return 200 | Pass on the seven named routes plus `/retail-pos` |
| Unique title, description, and one H1 in source for every `SEO_PAGES` entry | Pass via `scripts/seo-check.mjs` |
| One canonical on `https://axizpos.com` | Pass in source. Live samples had one canonical. |
| Public robots meta is `index, follow` | Pass on the sampled public URLs |
| No `X-Robots-Tag: noindex` on those public URLs | Pass on the sampled public URLs |
| Sitemap lists 107 canonical URLs and no private prefix | Pass in source tests and on the live file |
| `robots.txt` references `https://axizpos.com/sitemap.xml` and allows `/` | Pass on the live file |
| `www` 301s to the apex | Pass |
| Trailing slash 301s | Pass for `/cafe-pos/` |
| Query variant keeps the clean canonical | Pass for `/cafe-pos?utm_source=test` |
| Portal shell is `noindex` and omits customer data | Pass. `/login` HTML had no email, token, password, or customer string. |
| Console is `noindex, nofollow` | Pass for `/admin74246/` |
| Unpublished URLs 404 with `noindex` | Pass for `/pharmacy-pos`, `/privacy`, `/about` |
| Live 404 also sends `X-Robots-Tag` | Not on the live response. Present on the internal 404 location in source nginx. |
| HTTP redirects to HTTPS | Not done. Port 80 returned 200. Left unchanged. |
| Hardware product paths do not replace the `/hardware` canonical in the browser | Fixed in source. Live HTML still canonicalises to `/hardware` before JavaScript. The old script is gone only after a marketing deploy. |
| Structured data has no invented ratings or reviews | Pass in `scripts/seo-check.mjs` |
| Core Web Vitals field data | Not run |
| Search Console indexed count | Not verified. The supplied report says 8 indexed and 2 not indexed. The two URLs were not named. |

## Commands

- `node scripts/seo-check.mjs`
- `pnpm --filter @ai-pos/site exec vitest run src/indexability.test.ts`
