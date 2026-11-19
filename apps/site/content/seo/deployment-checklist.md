# Marketing deploy checklist

Do not deploy from this file until the HTTP decision below is accepted. This deploy is the marketing site only. Do not restart the API, the portal, or the console as part of it.

## Build

From `apps/site`, with the environment variables below present or deliberately empty:

```
npm run build
```

The build writes `apps/site/dist`, including `sitemap.xml`, `robots.txt`, and `404.html`.

## Environment variables

Set these only in the build environment. Do not commit the values.

| Variable | Required | Effect if empty |
| --- | --- | --- |
| `VITE_GA_MEASUREMENT_ID` | No | No GA4 tag. Use this empty when Tag Manager will own GA4. |
| `VITE_GOOGLE_SITE_VERIFICATION` | No | No Search Console meta tag. DNS verification does not need it. |
| `VITE_BING_SITE_VERIFICATION` | No | No Bing meta tag. |

Do not set both a GA4 measurement ID and a Tag Manager container for the same site.

## Files to publish

Copy `apps/site/dist` to `/var/www/ai-pos-site` on the host. Do not replace `/var/www/ai-pos-admin`.

Copy the reviewed nginx snippets to `/etc/nginx/snippets/` and reload nginx only after `nginx -t` succeeds. The repository copies are:

- `deploy/nginx/ai-pos.apex.conf` includes the `/home-3` redirect and the marketing 404.
- `deploy/nginx/ai-pos.conf` is unchanged. HTTP still serves the site.
- `deploy/nginx/proposed/ai-pos.http-to-https.conf` is not installed. Install it only after port 443 is confirmed open, and keep `/.well-known/acme-challenge/` on port 80.

## Rollback

Keep the previous `/var/www/ai-pos-site` directory. If the new pages mis-serve, put that directory back and reload nginx with the previous `ai-pos.apex.conf`. The portal and API are separate processes and do not need a rollback for a marketing-only revert.

## Checks after the files are live

```
curl -sI https://axizpos.com/cafe-pos
curl -sI https://axizpos.com/home-3
curl -sI https://axizpos.com/pharmacy-pos
curl -sI https://axizpos.com/sitemap.xml
curl -s https://axizpos.com/robots.txt
```

Expect 200 for café, 301 from `/home-3` to `https://axizpos.com/`, and 404 for `/pharmacy-pos` with the marketing not-found page. Expect the sitemap to list 107 URLs and no `/home-3`.

Search Console and GA4 are still not connected until the steps in `search-setup.md` are done by the account owner.
