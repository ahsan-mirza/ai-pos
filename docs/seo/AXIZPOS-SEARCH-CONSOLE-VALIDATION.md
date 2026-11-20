# Search Console validation

Do this in the `axizpos.com` property after a marketing deploy. A successful live test is not indexing. Google does not promise to index a URL because indexing was requested.

1. Open the property `sc-domain:axizpos.com` or the prefix `https://axizpos.com/`. Confirm the owner is the business account.
2. Open Page indexing. Record the indexed count and the not-indexed count.
3. Export the exact URL excluded by `noindex`.
4. Export the exact URL that is discovered and currently not indexed.
5. Inspect each URL. Record the Google-selected canonical and the user-declared canonical.
6. Classify each URL with the labels in `AXIZPOS-GSC-INDEXING-ISSUES.md` before changing it.
7. After the classification is public and the page is deployed, run Test live URL.
8. Confirm the live test allows indexing only when the decision is `PUBLIC — SHOULD BE INDEXED`.
9. Request indexing only for that canonical `https://axizpos.com` URL.
10. Use Validate fix when the report offers it.
11. Watch the report. Leave the validation state as Not Started until Google changes it.

Do not request indexing for `/login`, `/signup`, `/dashboard`, `/inventory`, `/admin74246/`, `/api/`, `/pharmacy-pos`, `/privacy`, `/about`, or any other private or unpublished URL.

Do not bulk-request the 107 sitemap URLs.

The sitemap to submit, if it is not already submitted, is `https://axizpos.com/sitemap.xml`.
