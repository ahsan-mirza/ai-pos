# Route indexability matrix

The decision function is `classifyPath` in `apps/site/src/indexability.ts`. Public URLs are `SEO_PAGES` in `apps/site/src/seo.ts`. On 20 November 2026 the source list and the live sitemap both contained 107 URLs.

## Public — should be indexed

These return HTTP 200 on `https://axizpos.com`, use one self canonical, send `index, follow`, and are in `sitemap.xml`. Arabic pairs exist for the translated pages. `/ai-pos` has no Arabic URL.

| Path | Purpose |
| --- | --- |
| `/` | Product home |
| `/explore` | Shared demos |
| `/hardware` | Published hardware catalogue |
| `/cafe-pos` | Café counter, modifiers, tabs |
| `/restaurant-pos` | Tables, kitchen, split bills |
| `/grocery-pos` | Supermarket and grocery. `/supermarket-pos` redirects here |
| `/electronics-pos` | IMEI, serials, warranties, repairs |
| `/fashion-pos` | Size and colour |
| `/wholesale-pos` | Tier prices, credit, partial delivery |
| `/quick-service-pos` | Counter and delivery channels |
| `/retail-pos` | Shared catalogue checkout |
| `/pos-software-uae` | UAE setup, AED, VAT report |
| `/offline-pos` | Desktop register after one connection |
| `/inventory-management` | Stock, purchase orders, transfers |
| `/multi-branch-pos` | More than one store |
| `/imei-serial-tracking` | Device serials |
| `/kitchen-display` | Kitchen tickets |
| `/loyalty-promotions` | Points and promotions |
| `/ai-pos` | Assistant limits |
| `/blog` and the guide URLs in the sitemap | Guides |
| `/ar` and the Arabic paths in the sitemap | Arabic versions of translated pages |

There is no separate public URL for pricing, features, about, contact, or privacy. `/pricing`, `/features`, `/solutions`, `/industries`, and `/contact` redirect to homepage sections. About and privacy are not published.

## Private — should not be indexed

The portal shell in `apps/web/index.html` sends `noindex, follow`. The console sends `noindex, nofollow`. These prefixes are application routes. They are absent from the sitemap. Authentication still runs in the portal. `noindex` does not replace it.

`/login`, `/signup`, `/forgot-password`, `/recover-store-code`, `/welcome`, `/demo`, `/kds`, `/table`, `/m`, `/inventory`, `/dashboard`, `/account`, `/subscription`, `/terminals`, `/customers`, `/sales`, `/fulfillment`, `/sales-orders`, `/reorders`, `/rentals`, `/repairs`, `/returns`, `/users`, `/warranties`, `/margin`, `/expenses`, `/payables`, `/consignment`, `/staff`, `/assistant`, `/accounting`, `/bank`, `/insights`, `/sales-insights`, `/reports`, `/einvoicing`, `/analytics`, `/promotions`, `/trade-ins`, `/store-credit`, `/gift-cards`, `/payments`, `/cheques`, `/shifts`, `/reach`, `/stores`, `/roles`, `/settings`, `/registers`, `/downloads`, `/deliveries`, `/admin`, `/admin74246`.

`/api/` is not a document. `robots.txt` disallows it.

`robots.txt` also disallows `/login`, `/signup`, `/forgot-password`, `/recover-store-code`, `/dashboard`, and `/admin74246/`. That list is unchanged until the Search Console URLs are known.

## Duplicate — canonicalize

| URL shape | Canonical |
| --- | --- |
| Query strings on a public page, such as `?utm_source=` | The public path without the query. Live `/cafe-pos?utm_source=test` already does this. |
| `/hardware/products/{slug}` and `/hardware/packages/{slug}` | `https://axizpos.com/hardware`. The catalogue HTML is the indexable document. |

## Redirect — consolidate

| From | To |
| --- | --- |
| `/supermarket-pos` | `/grocery-pos` |
| `/home-2`, `/home-3` | `/` |
| `/pricing`, `/solutions`, `/features`, `/industries`, `/contact` | `/#{section}` |
| `/ai`, `/copilot` | `/#intelligence` |
| A trailing slash or `/index.html` on a landing page | The slashless path |
| `https://www.axizpos.com/...` | `https://axizpos.com/...` |

## Invalid — remove from sitemap

`/pharmacy-pos`, `/privacy`, `/about`, `/terms`, `/refund`, and `/home` are not pages. Nginx returns the marketing 404. They are not in the sitemap. Do not add them in order to clear a `noindex` report.

`http://axizpos.com/` currently returns 200. Its canonical is `https://axizpos.com/`. Forcing HTTPS on port 80 is a separate deploy decision and was not changed.
