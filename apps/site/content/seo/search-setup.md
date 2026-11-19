# Search Console, analytics, and webmaster setup

These steps need an account the business owns. Do not put verification tokens, measurement IDs, or API secrets in source code. Set them in the deployment environment. The marketing build reads them at build time and omits the tag when the value is missing or the wrong shape.

Live check on 19 November 2026: `https://axizpos.com/` returned no `google-site-verification` meta tag and no Google tag. Search Console indexation and rankings are therefore not verified from this repository.

## Google Search Console

1. Open [Google Search Console](https://search.google.com/search-console) with the Google account that should own `https://axizpos.com`.
2. Add a Domain property for `axizpos.com`, not only the `www` host. The site already redirects `https://www.axizpos.com` to `https://axizpos.com`.
3. Verify with the DNS TXT record Google shows. This requires the person who controls DNS. Do not change other DNS records.
4. After DNS verification, also add the URL-prefix property `https://axizpos.com/` if you want the HTML-tag method as a backup.
5. For the HTML tag, copy only the `content` value. Set `VITE_GOOGLE_SITE_VERIFICATION` in the environment used to build `apps/site`, then rebuild and deploy the marketing site. The tag is emitted only when the value is 8–128 characters of letters, digits, `_`, or `-`.
6. Submit `https://axizpos.com/sitemap.xml`.
7. Use the indexation checklist in `indexation-checklist.md`. Do not treat a page as indexed because it opens in a browser.

## Google Analytics 4

1. Create a GA4 property for AxizPOS in the same Google account.
2. Create a Web data stream for `https://axizpos.com`.
3. Copy the Measurement ID (`G-` followed by letters and digits). Set `VITE_GA_MEASUREMENT_ID` for the marketing build. The site loads gtag only when the ID matches that shape.
4. Rebuild and deploy. Confirm the network request in a browser you control. Do not commit the ID if the team treats it as an environment secret. It is not a password, but it does not belong in a screenshot of server secrets either.
5. Mark these `dataLayer` events as key events after they appear in DebugView. The site already pushes them. No names, emails, or phone numbers are included.

| Event | Meaning |
| --- | --- |
| `view_page` | A marketing document loaded. `page_path` is the path. |
| `view_industry_page` | A solution, feature, or guide body rendered. |
| `click_get_started` | Get Started Free. This opens registration. A new store starts on the Free plan. It is not a separate trial promise. |
| `click_book_demo` | Book a demo. |
| `click_explore_plans` | Pricing link. |
| `click_contact_sales` | Contact sales, where that control is used. |
| `whatsapp_click` | WhatsApp, only when the console has published a number. |
| `contact_form_submit` | The enquiry form was submitted. |
| `click_billing_period` | A pricing period control. |

6. In GA4, build an exploration that filters Session default channel group to Organic Search. Separate landing pages. Branded queries are the ones containing `axizpos`. Non-branded commercial queries are the others. Search Console, not GA4, is the source for the query text.

## Google Tag Manager

Use Tag Manager only if it will own the GA4 tag. Do not install both a GTM container and `VITE_GA_MEASUREMENT_ID`. Two tags double-count page views.

If you choose Tag Manager:

1. Create a container for `https://axizpos.com`.
2. Leave `VITE_GA_MEASUREMENT_ID` empty so the site does not emit its own gtag snippet.
3. The container snippet is not in the repository yet. Add it in the marketing head only after the container ID exists, and map the `dataLayer` events above to GA4 event tags.
4. Publish the container in GTM. A draft container does not collect data.

## Bing Webmaster Tools

1. Open [Bing Webmaster Tools](https://www.bing.com/webmasters) and add `https://axizpos.com`.
2. Prefer the DNS CNAME or XML file method if DNS is available.
3. For the meta-tag method, copy the `content` value of `msvalidate.01`. Set `VITE_BING_SITE_VERIFICATION` to that hex string (16–64 hex characters) and rebuild. The site emits `<meta name="msvalidate.01">` only when the value matches.
4. Submit `https://axizpos.com/sitemap.xml`.

## Conversion definitions

Mark a key event only when the action the event describes has happened. Do not mark clicks that only open a dialog as completed leads.

| Event | When it fires | Treat as a completed lead |
| --- | --- | --- |
| `whatsapp_click` | The visitor activates a WhatsApp link. The number is the one the console published. | Yes |
| `contact_form_submit` | The contact form validated and the browser was asked to open WhatsApp with that note. It does not prove the WhatsApp message was sent. | Yes, as a qualified attempt |
| `click_book_demo` | Book a demo was clicked and the enquiry dialog opened. | No. Wait for `contact_form_submit` |
| `click_contact_sales` | Contact sales was clicked. | No. Wait for `contact_form_submit` |
| `click_explore_plans` | A pricing link was used. | No. This is a pricing visit |
| `click_get_started` | Get Started Free was clicked. Registration opens. A new store starts on the Free plan. | No. This is not a completed trial |

WhatsApp numbers to publish in the console are +971505007433 and +923227866684. The site does not hard-code them. Email is info@axizpos.com when the console publishes it. The website is https://axizpos.com.

## After the marketing deploy

These steps are not done. Do them only after the new build is on https://axizpos.com.

1. Fetch `/robots.txt`, `/sitemap.xml`, `/`, `/cafe-pos`, `/restaurant-pos`, `/grocery-pos`, `/ai-pos`, `/home-3`, `/pharmacy-pos`, and `/about`. Confirm HTTPS, the sitemap count, self-canonicals, the homepage redirects, and a real 404 for unpublished URLs.
2. In Search Console, submit `https://axizpos.com/sitemap.xml`. Inspect the homepage, café, restaurant, grocery, retail, and AI POS URLs. Record the verdict. Do not bulk-request indexing.
3. Export Performance for the longest available range. That file is the baseline. Save impressions, clicks, queries, and pages. Split queries containing `axizpos` from the rest.
4. In GA4 DebugView, complete one WhatsApp click, one pricing click, and one contact form. Confirm the events above. Do not count a demo until the form event fires.
5. After 28 days, compare the new Performance export with the baseline. Note which landing pages gained impressions. Do not describe that comparison as a ranking guarantee.
