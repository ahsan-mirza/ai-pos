# Restaurant and cafe menu pricing variants

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

A menu item can keep one base price or carry several named base prices. The cashier must choose one option before a multi-price item is added. Modifiers stay add-ons on top of that choice. Availability schedules were not added.

Restaurant and cafe now also store a product-level ingredient mode. New lines follow that setting. The combined flow is in `RESTAURANT-PORTION-PRICING-ACCEPTANCE.md` and `RESTAURANT-PREPARED-ITEM-RECIPE-TOGGLE-ACCEPTANCE.md`.

## Model

`menu_price_options` belongs to one product inside the tenant. Each row has a stable id, a name, a price in cents, an optional SKU, an active flag, and a display position. Migration `20261122_0133_menu_price_options` creates the table and adds `price_option_id`, `price_option_name`, and `price_option_cents` to `sale_items` and `open_order_items`.

Zero active options, or fewer than two, keeps the existing single price on `products.price_cents`. Two or more active options are the multiple-price mode. Option names are data. Breakfast, Lunch, Dinner, and plate sizes are not hard-coded.

An option that already appears on a sale or an open order is deactivated when it is removed from the editor. It is not deleted. A later menu edit does not rewrite `sale_items.unit_price_cents` or `price_option_cents`.

## Configuration

An authorized user with portal inventory management calls:

- `GET /api/v1/menu/products/{product_id}/price-options`
- `PUT /api/v1/menu/products/{product_id}/price-options`

The business portal shows the editor on the menu modifiers page as **Priced options**. Blank names, duplicate names, a negative price, and a list with exactly one active option are rejected. Saving an empty list returns the item to its single price.

A cashier token does not gain this permission. The route uses the existing inventory-manage dependency.

## Cashier flow

`ProductCard` shows `From` and the lowest active option price when the item has at least two active options. It does not show a chosen option before the cashier picks one.

`PriceOptionModal` opens before the item is added. No option is selected by default. Add stays blocked until one active option is chosen. Cancel leaves the cart unchanged. The chosen quantity is kept while the cashier changes the option. Modifier groups for that item appear after a base option is selected. The line unit price is the option price plus the existing modifier deltas. A second click while the confirm is in progress is ignored.

A single-price restaurant or cafe item adds immediately, including the existing modifier dialog when the item has modifiers. The till does not ask whether ingredients are required. That choice is `products.sell_without_recipe`, saved on the menu item. The line stores it as `skip_recipe`. The option price and the modifier deltas do not change because ingredient consumption was skipped.

Other business types, including quick service, still open this dialog for a recipe-linked item so a permitted user can choose Ingredients Required or Ingredients Not Required. See `RESTAURANT-INGREDIENT-REQUIREMENT-ACCEPTANCE.md`.

## Cart, ticket, and sync

The cart line stores the option id, name, and base price. `priceSnapshotCents` keeps a later catalogue price from replacing the line. Changing the option on an unpaid line recalculates from the newly chosen option price plus the current modifiers. The sale payload sends `price_option_id` on the existing sale item. There is no second sync queue.

Open table tickets store the same snapshot in `table_session_items.price_option_json`. That column is added on the register database when the desktop schema migrates. A live register restart was not exercised in this pass. The ingredient mode is stored separately as `skip_recipe` and is not inferred from the price option. Recipes are one row per product. A Full Plate and a Small Plate use that same recipe, scaled by the line quantity and the recipe yield. Portion-specific ingredient quantities were not added.

## Server validation

The option must belong to the product. A multi-price item without an option is rejected. The charged base must equal the option's current price or a price already published for that option id on the catalogue change feed. A price that was never published is rejected. A previously published price is accepted after the live price changes, and the sale row keeps the submitted unit price. Modifier deltas still come from the modifier catalogue.

`tests/test_menu.py::test_priced_options_are_required_and_snapshotted` covers configuration, a missing choice, a forged price, a valid Breakfast line, and a replay at the previously published 800 cents after the live Breakfast price moved to 900 cents. The stored sale stayed at 800 cents.

## What was not built

Availability schedules, business-timezone windows, and overnight windows were not added. An option is available when it is active. Scheduling stays a separate extension.

Branch-specific option prices were not added. Options follow the existing tenant menu.

## Tests in this pass

`node scripts/python.mjs --env=test -m pytest tests/test_menu.py -q --tb=short`

3 passed, 0 failed, exit 0. Duration 4.46s. This is the menu file only.

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/catalogCard.test.ts src/features/checkout/cataloguePreference.test.ts src/features/checkout/catalogueView.test.tsx src/components/RegisterLayout.test.ts src/components/shell/posControls.test.ts src/features/settings/settingsRoutes.test.ts src/features/checkout/catalogProfileAcceptance.test.tsx src/features/checkout/cart.test.ts --reporter=dot`

8 files, 55 tests, 0 failed, exit 0.

`pnpm --filter @ai-pos/desktop lint` (`tsc` and `eslint`) exit 0.

`pnpm --filter @ai-pos/web lint` exit 0.

`pnpm --filter @ai-pos/shared-types typecheck` exit 0.

`cargo check --offline --quiet` in `apps/desktop/src-tauri` exit 0. Existing warnings only. `cargo test` was not run.

The full API pytest suite was not run.

## Limitations

- Selector zoom was recorded later in `RESTAURANT-PRICING-SELECTOR-ZOOM-ACCEPTANCE.md`. This pricing pass still did not click a live Restaurant window, restart it, or sync a priced line.
- Restaurant and cafe no longer ask the cashier to choose ingredients. The product toggle is authoritative for new lines.
- Schedules are not implemented.
- The Laundry till and production records were not modified.
