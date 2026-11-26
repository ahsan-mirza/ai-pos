# Restaurant and cafe portion pricing

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

One restaurant or cafe menu item can carry several named portion prices. Portions are not separate products. Modifiers stay separate. This status is only the pricing behavior. The prepared-item toggle is in `RESTAURANT-PREPARED-ITEM-RECIPE-TOGGLE-ACCEPTANCE.md`. The live register walk is in `RESTAURANT-NATIVE-END-TO-END-ACCEPTANCE.md`. Recipe draw, shortfall, and the remaining checkout gaps are in `RESTAURANT-CAFE-RECIPE-CHECKOUT-OFFLINE-ACCEPTANCE.md`. Takeaway and delivery are in `RESTAURANT-TAKEAWAY-DELIVERY-OFFLINE-ACCEPTANCE.md`.

## Product entry

The register product form and the business portal product form share the inventory product APIs. For a made-to-order item the register form has **Pricing & Portions**.

- Leaving the rows blank keeps the single base price on `products.price_cents`. Mineral Water at AED 2.00 is that path. The till adds it without a portion dialog.
- Two or more named rows save `menu_price_options` on that one product. Daal Channa can be Small Plate 300 cents, Medium Plate 500 cents, and Full Plate 900 cents.
- Each row has a name, a price, an active flag, and an order. The form can add a row, edit it, move it up or down, deactivate it, or remove it. Names are not hard-coded.
- A filled list needs at least two named prices, at least one active row, and no duplicate names. Money uses the existing cent conversion, at most two decimal places.
- An option already used on a sale or an open order is deactivated instead of deleted. That rule was already in `replace_price_options`.

The portal **Priced options** panel already edited the same rows, including the active flag. Cashiers do not have `portal:inventory_manage`, so they cannot change the prices.

On 26-11-2026 the Business Pro add and edit menu item form gained **Pricing & Portions** for restaurant and cafe. It writes this same API. The modifiers screen still has the priced-options panel. See `BUSINESS-PRO-RESTAURANT-CAFE-PORTION-PRICING-ACCEPTANCE.md`.

## Till

`CatalogTile` is unchanged. A single-price card shows its price. A multi-price card shows `From` and the lowest active portion price. The card does not select a portion. Restaurant and cafe cards still omit the branch-stock footer.

A multi-price item with no modifier groups opens the quantity modal and shows its portions there. No portion starts selected. Add stays disabled until one is chosen. Items that also have modifiers still use `PriceOptionModal`, which now uses the same quantity stepper. Cancel does not change the cart. Confirm adds one line and ignores a second click while saving. Different portions stay different lines. An unpaid line can be given another portion. The stored price is the portion base plus the existing modifier deltas. See `RESTAURANT-UNIFIED-QUANTITY-PORTION-MODAL-ACCEPTANCE.md`.

A single-price restaurant or cafe item does not open this dialog only because it has a recipe. Modifier groups still open the modifier dialog.

## Snapshot

The line keeps the menu item id, the pricing-option id, the option name, the option base price, the quantity, the modifier snapshots, tax and discount values, and the line total. A later edit of the menu price does not rewrite a stored sale row. That replay rule is the existing priced-option test: a published 800-cent option still settles at 800 after the live price moves to 900.

## What this pass did not prove

No live Restaurant window was opened. Catalogue selection, the portion dialog, and cart persistence were not clicked on a register. The API test created the three Daal Channa portions and settled Full Plate at 900 cents with `price_option_name` Full Plate and `price_option_cents` 900. The desktop selector tests cover the dialog markup, not a native window.

Schedules and branch-specific option prices are still absent. Portions share one recipe. See the prepared-item report.

## Tests

`node scripts/python.mjs -m pytest tests/test_menu_recipe_mode.py tests/test_recipes.py tests/test_menu.py -q --tb=line`

8 passed, 0 failed, exit 0. About 8.3 seconds. The new case is `test_prepared_toggle_is_authoritative_for_new_lines`, which also saves Small Plate 300, Medium Plate 500, and Full Plate 900.

From `apps/desktop`:

`pnpm exec vitest run src/features/inventory/menuEntry.test.ts src/features/inventory/productPayload.test.ts src/features/checkout/priceOptionModal.test.tsx src/features/checkout/cart.test.ts --reporter=dot`

4 files, 34 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` in `apps/desktop` exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` in `apps/web` exit 0.

`cargo check --offline` in `apps/desktop/src-tauri` exit 0.

`cargo test --offline --lib` with `POS_ENV=development`: 79 passed, 0 failed, exit 0. An earlier run in the same shell failed one zoom test because `POS_ENV` was `acceptance` and the crate compiled as an acceptance build. That is not a portion-pricing failure. The development rerun passed, including `production_builds_ignore_zoom_files`.

The full API suite was not run. No production database was migrated or sold against.
