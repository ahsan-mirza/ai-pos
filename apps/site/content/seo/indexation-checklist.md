# Indexation checklist

Checked against the public site on 19 November 2026 and against the marketing source after this change. "Indexed" is blank on purpose. Only Google Search Console, after verification, can fill that column. A 200 response is not indexation.

| URL | Accessible on 19 Nov 2026 | Indexable in HTML | Canonical | Internal links | In the live sitemap that day | Unique intent | Indexed in Search Console |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `/` | 200 | yes, index follow | self | navigation | yes | Home | Not verified |
| `/cafe-pos` | 200 | yes | self | footer and home | yes | Café counter, modifiers, tabs | Not verified |
| `/restaurant-pos` | 200 | yes | self | footer and home | yes | Tables, kitchen, split bills | Not verified |
| `/grocery-pos` | 200 | yes | self | footer and home | yes | Barcode, weight, expiry-first | Not verified |
| `/electronics-pos` | 200 | yes | self | footer and home | yes | IMEI, warranty, repairs | Not verified |
| `/fashion-pos` | 200 | yes | self | footer and home | yes | Size and colour | Not verified |
| `/wholesale-pos` | 200 | yes | self | footer and home | yes | Tier prices, credit, partial delivery | Not verified |
| `/quick-service-pos` | 200 | yes | self | footer | yes | Counter and delivery channels | Not verified |
| `/retail-pos` | 200 | yes | self | footer | yes | Shared catalog checkout, not fashion or grocery | Not verified |
| `/blog` and the blog posts in the live sitemap | 200 for `/blog` | yes | self | footer | yes, 9 English posts and Arabic pairs | Guides | Not verified |
| `/pos-software-uae` | 200 | yes | self | footer | yes | UAE setup, not a city page | Not verified |
| `/home-2` | 301 to `/` | n/a | n/a | no | no | Retired | Not verified |
| `/home-3` | 200 | was indexable | was self | design preview | was listed | Duplicate of the home intent | Not verified |
| `/pharmacy-pos` | 200 app shell, `noindex` | no | none | no | no | Not a pharmacy product page | Not verified |
| `/ai-pos` | not on the live deploy | source is indexable | self, in source | footer after deploy | no | Assistant limits | Not verified |
| `/privacy` and `/about` | 200 app shell, `noindex` | no | none | no | no | Not published legal or about pages | Not verified |

## After the next marketing deploy

- `/home-3` should send `noindex, follow` and a canonical of `https://axizpos.com/`, and it should be absent from `sitemap.xml`.
- `/ai-pos` should return 200, with one H1, a self canonical, and `index, follow`. It has no Arabic URL until a person reviews a translation. Do not add hreflang for a page that does not exist.
- `/supermarket-pos` should keep redirecting to `/grocery-pos`.
- Unknown paths such as `/pharmacy-pos` still fall through to the Business Pro shell. That shell is `noindex`. It is a soft 200, not a pharmacy landing page. Do not add a pharmacy URL.

## Search Console checks, in order

1. Confirm the property is `sc-domain:axizpos.com` or the `https://axizpos.com/` prefix, and that the verifying user is the business owner.
2. Open Pages, and record Indexed and Not indexed. Export the reasons. A page in the sitemap can still be Discovered, not indexed.
3. Inspect the homepage, `/cafe-pos`, `/restaurant-pos`, `/grocery-pos`, `/retail-pos`, and `/ai-pos` with URL Inspection. Record the verdict and the user-declared canonical versus the Google-selected canonical.
4. Open Sitemaps and confirm `https://axizpos.com/sitemap.xml` was read, and the URL count matches the deployed file.
5. Open Performance. Filter by query. Split queries that contain `axizpos` from the rest. Export the non-branded queries before calling this the baseline.
6. Do not request indexing in bulk. Use URL Inspection for the new `/ai-pos` URL once, after it is on the production host.
