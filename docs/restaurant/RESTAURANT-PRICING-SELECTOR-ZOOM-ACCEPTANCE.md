# Restaurant pricing-selector zoom acceptance

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

This pass does not change the status of the pricing-variant implementation in `RESTAURANT-MENU-PRICING-VARIANTS.md`. It records whether the existing `PriceOptionModal` stays usable at measured WebView zoom.

The window was AxizPOS Restaurant Zoom, identifier `com.axizpos.restaurant.zoom`, process 14648, window handle 2428844, data directory `%APPDATA%\com.axizpos.restaurant.zoom`. The menu came from the disposable API on `127.0.0.1:18093` and SQLite `%TEMP%\axiz-zoom\restaurant\axizpos_zoom_restaurant.sqlite`. No production menu row was edited. No order was settled.

Zoom measurement is the same method as [../ui-ux/POS-MULTI-PROFILE-ZOOM-ACCEPTANCE.md](../ui-ux/POS-MULTI-PROFILE-ZOOM-ACCEPTANCE.md): WebView2 zoom factor, `devicePixelRatio` ratio 1.0 / 1.25 / 1.5 / 2.0, `visualViewport.scale` 1, root font `16px`.

## Selector matrix

| Selector case | 100% | 125% | 150% | 200% |
| --- | --- | --- | --- | --- |
| Breakfast/Lunch/Dinner | PASS | PASS | PASS | PASS |
| Small/Medium/Large plate | PASS | PASS | PASS | PASS |
| Existing modifiers | PASS | PASS | PASS | PASS |
| Long labels and large prices | PASS | PASS | PASS | PASS |

Every cell opened the real dialog. The dialog text contained “No option selected” before a choice, so no option was pre-selected. Screenshots:

- Meals: `docs/ui-ux/zoom-evidence/restaurant-meal-100.png`, `restaurant-meal-125.png`, `restaurant-meal-150.png`, `restaurant-meal-200.png`
- Plates: `docs/ui-ux/zoom-evidence/restaurant-plate-100.png`, `restaurant-plate-125.png`, `restaurant-plate-150.png`, `restaurant-plate-200.png`
- Long names: `docs/ui-ux/zoom-evidence/restaurant-long-100.png`, `restaurant-long-125.png`, `restaurant-long-150.png`, `restaurant-long-200.png`
- Line after add: `docs/ui-ux/zoom-evidence/restaurant-line-100.png`

## What was visible

Breakfast, Lunch, and Dinner show `$8.00`, `$12.00`, and `$15.00` beside the names. Those amounts were read from the 100%, 125%, 150%, and 200% meal captures. Small Plate `$8.00` and Medium Plate `$11.00` were read from the 100% plate capture. The plate prices are the configured 800, 1100, and 1400 cents. At 200% the long-name item shows Regular Plate `$10.00` and Large Plate `$14.00` without the price overlapping the label. The long option name and the `$2,500.00` / `$3,200.00` options are further down that list.

The catalogue card for a multi-price item shows From and the lowest active price (Fresh Juice From USD 3.00, Grilled Chicken From USD 8.00). A single-price item shows its own price. The restaurant card has no branch-stock footer.

## Cancel, add, and the line

The dialog text includes Cancel, Add to order, and “No option selected” while the choice is empty. Add stays disabled until a choice exists; that disable rule is in `PriceOptionModal` and in `priceOptionModal.test.tsx`. The harness clicks Cancel between the zoom shots, then at 100% selects Breakfast and Extra cheese and clicks Add to order. The running page text then contains the Grilled Chicken line and Breakfast. An earlier read of that page text also showed Extra cheese `+$1.50` and a line total of USD 9.50, which is the $8.00 option plus the $1.50 modifier. The ticket was not settled.

In the captured frames, the option list reaches the bottom edge of the window before Cancel and Add to order. That is true at 100% and at 200%. The buttons are in the document and the harness can activate them. They are not in the visible window in those screenshots. The list itself does not show a horizontal scrollbar, and the prices do not collide with the names.

## Persistence

This pass did not restart the app, reopen a saved ticket, or edit a menu price to prove an existing ticket keeps its snapshot. Those checks remain as previously implemented. They were not repeated here, and no sale was charged to prove them.

## Correction

The first captures showed the option names and not the prices. The price element was at the far end of a full-width row. The dialog is now capped at `max-w-xl`, its height is capped at the overlay, and the price is the next text after the option name. After that change the captures above show the prices. `CatalogTile`, rem tokens, stock, allocation, and modifier calculation were not redesigned.

## Tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/priceOptionModal.test.tsx --reporter=dot`

1 file, 1 test, 0 failed, exit 0.

The shared catalogue suite was run again from `apps/desktop` and passed 7 files, 33 tests, exit 0. `pnpm exec tsc -p tsconfig.json --noEmit` exited 0.

## Limitations

- Cancel and Add to order are below the visible window edge in the 100% and 200% selector captures.
- The long `$2,500.00` and `$3,200.00` options were not the rows in the first screen of the 200% long-name capture. Regular Plate `$10.00` and Large Plate `$14.00` were.
- Restart persistence and “a later menu-price edit does not rewrite a saved ticket” were not rerun.
- No order was settled. The laundry till and production menu data were not used.
