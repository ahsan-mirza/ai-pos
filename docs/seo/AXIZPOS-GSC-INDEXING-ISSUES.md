# Search Console indexing issues

The report given with this work says the `axizpos.com` property has 8 indexed pages and 2 not indexed. One is excluded by a `noindex` tag. One is discovered and currently not indexed. Both validations are Not Started.

The screenshot does not name the URLs. Searches of the repository found no Search Console export, coverage CSV, or URL Inspection file. The earlier note in `apps/site/content/seo/indexation-checklist.md` also leaves the Indexed column as not verified.

These two rows stay `AWAITING URL EVIDENCE`. Their indexing behaviour was not changed.

| Field | Excluded by `noindex` | Discovered — currently not indexed |
| --- | --- | --- |
| Full URL | Not in the repository or in a supplied export | Not in the repository or in a supplied export |
| Report reason | Excluded by `noindex` tag, as stated. The URL itself is unknown. | Discovered — currently not indexed, as stated. The URL itself is unknown. |
| Google-selected canonical | Unknown | Unknown |
| User-declared canonical | Unknown | Unknown |
| Last crawl | Unknown | Unknown |
| HTTP status | Not inspected. The URL is unknown. | Not inspected. The URL is unknown. |
| Robots meta | Unknown | Unknown |
| `X-Robots-Tag` | Unknown | Unknown |
| `robots.txt` | Unknown | Unknown |
| Sitemap | Unknown | Unknown |
| Authentication | Unknown | Unknown |
| Redirect | Unknown | Unknown |
| Page purpose | Unknown | Unknown |
| Decision | `AWAITING URL EVIDENCE` | `AWAITING URL EVIDENCE` |

## What the property owner needs to collect

Open the property that is either `sc-domain:axizpos.com` or the URL-prefix property `https://axizpos.com/`.

1. Open Page indexing.
2. Export the URL under Excluded by `noindex` tag.
3. Export the URL under Discovered — currently not indexed.
4. For each URL, open URL Inspection and record Google-selected canonical, user-declared canonical, last crawl, and the live test result.

Paste the two full URLs back with those fields. Do not request indexing until each URL is classified with one of:

- `PUBLIC — SHOULD BE INDEXED`
- `PRIVATE — SHOULD NOT BE INDEXED`
- `DUPLICATE — CANONICALIZE`
- `REDIRECT — CONSOLIDATE`
- `INVALID — REMOVE FROM SITEMAP`

## URLs that were checked and are not those two rows

These were inspected because older notes mentioned them. They are not identified as the Search Console rows.

| URL | Live result on 20 November 2026 | Decision if this were the reported URL |
| --- | --- | --- |
| `/pharmacy-pos`, `/privacy`, `/about` | 404, meta `noindex`, not in the sitemap | `INVALID — REMOVE FROM SITEMAP`. They are not published pages. |
| `/login`, `/signup`, `/dashboard`, `/inventory` | 200 portal shell, `noindex, follow`, not in the sitemap | `PRIVATE — SHOULD NOT BE INDEXED` |
| `/home-3` | 301 to `https://axizpos.com/` | `REDIRECT — CONSOLIDATE` |
| `/hardware/products/not-a-real-product` | 200, HTML canonical `https://axizpos.com/hardware` | `DUPLICATE — CANONICALIZE` |

None of these were switched to `index, follow`.
