# Multi-profile catalogue zoom acceptance

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

Grocery, Electronics, Fashion, and Restaurant/Cafe each ran in its own acceptance window. Zoom was WebView2 `SetZoomFactor` through the Tauri window API on an acceptance build. It was not a root font-size change, a CSS viewport shrink, operating-system display scaling, or a window resize. The laundry till and the already-open restaurant acceptance process were not used. No sale was charged and no ticket was settled.

## How zoom was measured

The acceptance host writes the requested factor and the webview reports `devicePixelRatio`, `visualViewport.scale`, and the root font size. On this machine the 100% baseline `devicePixelRatio` is 1.75 because the display is scaled to 175%. The zoom ratio is the reported `devicePixelRatio` divided by that baseline. `visualViewport.scale` stayed at 1, so this was not pinch page scale. The root font stayed `16px`, so the rem layout was not being faked by changing the root size.

| Requested | Measured ratio | devicePixelRatio | Scale | Root font |
| --- | ---: | ---: | ---: | --- |
| 100% | 1.0 | 1.75 | 1 | 16px |
| 125% | 1.25 | 2.1875 | 1 | 16px |
| 150% | 1.5 | 2.625 | 1 | 16px |
| 200% | 2.0 | 3.5 | 1 | 16px |

The same ratios were recorded for all four profiles. Document `scrollWidth` stayed within 8px of `clientWidth` at every level. A level is PASS only where that measurement was read back from the running webview.

## Isolated registers

Each window has its own bundle identifier, process, native handle, roaming data directory, and disposable API. The API is `http://127.0.0.1` on the port below, with its own SQLite file under `%TEMP%\axiz-zoom\<profile>\axizpos_zoom_<profile>.sqlite`. These databases are not the production database and not the laundry database.

| Profile | Identifier | Port | Process | Window handle | Data directory |
| --- | --- | ---: | ---: | ---: | --- |
| Grocery | `com.axizpos.grocery.zoom` | 18090 | 55456 | 12848528 | `%APPDATA%\com.axizpos.grocery.zoom` |
| Electronics | `com.axizpos.electronics.zoom` | 18091 | 38248 | 3544102 | `%APPDATA%\com.axizpos.electronics.zoom` |
| Fashion | `com.axizpos.fashion.zoom` | 18092 | 49764 | 14093034 | `%APPDATA%\com.axizpos.fashion.zoom` |
| Restaurant/Cafe | `com.axizpos.restaurant.zoom` | 18093 | 14648 | 2428844 | `%APPDATA%\com.axizpos.restaurant.zoom` |

Restaurant/Cafe is one catalogue mode. Cafe was not a fifth window. Each process reached `shift-open` and showed its own catalogue text before any zoom step. Window titles were AxizPOS Grocery Zoom, AxizPOS Electronics Zoom, AxizPOS Fashion Zoom, and AxizPOS Restaurant Zoom.

## Catalogue matrix

| Profile | 100% | 125% | 150% | 200% |
| --- | --- | --- | --- | --- |
| Grocery | PASS | PASS | PASS | PASS |
| Electronics | PASS | PASS | PASS | PASS |
| Fashion | PASS | PASS | PASS | PASS |
| Restaurant/Cafe | PASS | PASS | PASS | PASS |

Screenshots:

- `docs/ui-ux/zoom-evidence/grocery-100.png`, `grocery-125.png`, `grocery-150.png`, `grocery-200.png`
- `docs/ui-ux/zoom-evidence/electronics-100.png`, `electronics-125.png`, `electronics-150.png`, `electronics-200.png`
- `docs/ui-ux/zoom-evidence/fashion-100.png`, `fashion-125.png`, `fashion-150.png`, `fashion-200.png`
- `docs/ui-ux/zoom-evidence/restaurant-100.png`, `restaurant-125.png`, `restaurant-150.png`, `restaurant-200.png`

The cards are the shared `CatalogTile` in `ProductCard`. Grocery showed Zoom Bulk Oil at USD 12,345.67 with a 4 Pieces badge and a Branch stock footer, and a long product name at USD 4.50 with 12 Pieces. Electronics showed Zoom Display Wall, a long scanner name, USD 899.00, and an out-of-stock card. Fashion showed Zoom Longline Shirt, an in-stock badge, `$49.00–$54.00`, and Choose size & colour. Restaurant showed Fresh Juice as From USD 3.00, Grilled Chicken as From USD 8.00 with a modifiers badge, and House Salad at its single price. Restaurant cards did not render a branch-stock footer (`footerHeight` null). Stock-profile footers measured 38px, which is `2.375rem` at the unchanged 16px root. Image wells measured 112px, which is `7rem`.

## Limitations

- Fashion was the only profile whose measured card had an `img`, and that image used `object-fit: contain`. Grocery, Electronics, and Restaurant cards in the probe had no `img`, so contain was not observed there. Several wells show the empty-state icon or a colour swatch.
- The online cards show branch stock. They do not show “This register: 40 available”. That sentence is produced for an offline register session. The disposable API did create a register allocation of 40. This pass did not change that rule, and the sentence was not on the captured cards.
- At 150% and 200% the catalogue grid is scrolled before the capture so the cards are in frame. The shell, search field, and category controls remain in the same window. The search placeholder is clipped inside its field at the higher levels.
- No sale was created from these catalogues.

## Correction

The Restaurant pricing dialog was wider than the window, and the option price sat at the far end of the row where the capture showed no glyphs. `PriceOptionModal` now uses `max-w-xl` and places the price immediately after the option name. That correction is covered by `priceOptionModal.test.tsx` and by the selector report. It does not change `CatalogTile`, stock math, or modifier math.

## Tests

The modal regression was run from `apps/desktop`:

`pnpm exec vitest run src/features/checkout/priceOptionModal.test.tsx --reporter=dot`

1 file, 1 test, 0 failed, exit 0.

The previously passing desktop suite was run again from `apps/desktop`:

`pnpm exec vitest run src/features/checkout/catalogCard.test.ts src/features/checkout/cataloguePreference.test.ts src/features/checkout/catalogueView.test.tsx src/components/RegisterLayout.test.ts src/components/shell/posControls.test.ts src/features/settings/settingsRoutes.test.ts src/features/checkout/catalogProfileAcceptance.test.tsx --reporter=dot`

7 files, 33 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` exited 0. A unit test is not this zoom pass.

## Left untouched

The laundry register, its data directory, production tenants, stock, customers, and finance records were not modified. No deployment was made.
