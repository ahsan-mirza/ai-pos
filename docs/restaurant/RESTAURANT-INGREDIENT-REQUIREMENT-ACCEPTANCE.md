# Restaurant and cafe ingredient requirement

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

This status is separate from the four-profile zoom acceptance and from the pricing-variant status in `RESTAURANT-MENU-PRICING-VARIANTS.md`.

A recipe-linked menu item can be added with **Ingredients Required** or **Ingredients Not Required**. The choice belongs to that order line. It does not turn the recipe off for the item, and it does not change the line price.

## Existing flow

Raw ingredients are not reserved or deducted when a line is added to the cart or to an open table. `recipe_service.consume` runs from `record_sale`, after the sale row exists, through `fnb_service.consume_sale`.

For a line whose product has a recipe, or a combo part that has a recipe, the service scales each ingredient by the sold quantity and the recipe yield, applies modifier ingredient deltas, and draws `min(needed, available)` with a `RECIPE_OUT` stock movement (`reference_type` `sale_recipe`). It writes `recipe_usages` with `quantity_needed` and `quantity_drawn`, sets the sale-item cost, and records `recipe.stock_short` when the draw is short. The sale is not refused for a shortfall. Selling an ingredient product on its own is still refused. The prepared dish itself is not stocked.

Open orders (`order_service.create_order`, `add_items`, and the offline `open_order` sync) store lines and do not move ingredient stock. Sending an order fires kitchen tickets. Tickets do not move stock. Payment of an open order is an ordinary sale, and that sale is what consumes the recipe.

Catalogue products already carry `has_recipe`. The sell grid hides ingredient products. A recipe is one row per product (`recipes.product_id` is unique). Price options are a second base price, not a second recipe.

## What changed

- Permission `pos:skip_recipe`. Store Manager and Super Admin receive it. The Cashier role does not. It is not an inventory-adjust permission.
- `skip_recipe` on `sale_items`, `open_order_items`, and `kitchen_ticket_items`. Absent or false means Ingredients Required. True means this line does not consume its recipe.
- Migration `20261122_0134_skip_recipe` adds those columns with `server_default` false. Downgrade drops them. It was not applied to any database.
- `record_sale` rejects `skip_recipe: true` unless the cashier on the sale has `pos:skip_recipe`. Authorized skipped lines are left out of `sold_dishes`, so they create no `RECIPE_OUT` movement and no `recipe_usages` row. The sale still records `recipe.skip` with the user, store, sale, line, product, price option, quantity, and `ingredient_requirement: not_required`.
- Open-order create, add, and offline sync use the same permission check. A forged flag from a cashier is `403` on the HTTP routes and `SyncRejected` on sync. The line stores the flag and audits `recipe.skip`.
- Kitchen tickets copy the flag. The kitchen display and the ticket print show `No recipe ingredient consumption`. The line stays on the ticket, keeps its modifiers, and is not marked prepared.
- The cashier dialog `PriceOptionModal` shows the ingredient choice when `product.has_recipe` is true, together with a serving option when the item has two or more active prices, and with the existing modifiers. Ingredients Required is selected by default. Ingredients Not Required is disabled, with an explanation, when the signed-in user lacks `pos:skip_recipe`.
- Cart lines keep `skipRecipe`. Two lines that differ only in that flag do not merge. Quantity and modifier edits keep the flag. The unit price stays the option or product price plus modifier deltas.
- The sale payload sends `skip_recipe: true` only for a skipped line, on the existing sale event. Open-order items send the same field. There is no second queue.
- The register SQLite table `table_session_items` gains `skip_recipe INTEGER NOT NULL DEFAULT 0` on migrate. Existing local rows stay 0.

## Ingredients Required

The line is priced, taxed, and sent as before. On sale recording, the existing recipe, yield, and modifier quantities apply. A shortfall still records `recipe.stock_short` and does not refuse the sale. That is the rule this change preserved. Adding the line to a cart or a table still does not consume ingredients.

## Ingredients Not Required

The server accepts the line only when the acting user has `pos:skip_recipe`. It does not check ingredient availability for that line, does not reserve ingredients, and does not write a stock movement or a substitute movement. Price, tax, quantity, modifiers, and the selected price option stay on the normal path. The item's recipe row is unchanged. The next line that does not skip still uses that recipe.

Other checks still apply: the product must belong to the tenant and be sellable, the cashier must have POS access, price options and modifiers must belong to the item, and payment rules are unchanged.

## Direct sale

A cashier without the permission cannot push a skipped sale. An authorized cashier can. Replaying that sale with the same idempotency key does not create a second draw. A following sale of the same dish without the flag still writes `recipe_usages` and still allows the existing shortfall.

## Table orders

An unauthorized `user_id` cannot open a table with a skipped line and cannot add a skipped line to an open order. An authorized user can. The order stays `OPEN`. Reading the order back returns `skip_recipe: true` and the original unit price and quantity. Sending the order to the kitchen does not change ingredient on-hand. The ticket item carries `skip_recipe` and is not voided or marked ready by that choice.

## Offline

The choice is stored on the local table session and reloaded from SQLite. The sale and open-order sync payloads carry the same boolean. A missing `has_recipe` on a cached product does not send `skip_recipe`, so the server still applies a recipe if one exists. The register does not treat a failed request as permission to skip.

A live register was not restarted, and a disconnected till was not walked. The SQLite roundtrip and the API idempotent replay are the persistence evidence for this pass.

## PostgreSQL

The columns are additive on tables that are already tenant-scoped. No new RLS policy was added. Pytest uses `create_all` on SQLite, so this pass did not migrate a PostgreSQL database. The migration file is the PostgreSQL change. It must not be applied to a protected register database.

Historical rows default to false. That keeps their existing recipe handling. The migration does not insert stock movements or rewrite totals.

## Tests

`apps/api/.venv/Scripts/python.exe -m pytest tests/test_recipes.py -q --tb=line`

4 passed, 0 failed, exit 0. Duration 5.64s. The file includes the previous recipe-draw and shortfall tests plus the new permission, no-movement, replay, order, and kitchen checks.

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/cart.test.ts --reporter=dot`

1 file, 23 tests, 0 failed, exit 0. Duration 1.07s. The new case keeps a required line and a not-required line apart, keeps the flag when quantity and a modifier change, and keeps the modifier delta on the price.

`pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` from `apps/web` exit 0.

There is no `tsconfig.json` at the repository root, so the root command `pnpm exec tsc -p tsconfig.json --noEmit` cannot run.

From `apps/desktop/src-tauri`, with the existing `CARGO_TARGET_DIR` pointing at `acceptance/offline/target`:

`cargo test --offline --lib skip_recipe_survives_save_and_reload`

1 passed, 55 filtered out, exit 0. Duration 0.60s after a 21.06s compile. The full library suite was not run.

The full API pytest suite was not run.

## Limitations

- No Restaurant window was opened, so there is no screenshot of the dialog.
- App restart of a running register, and a real offline sync after reconnect, were not exercised.
- Recipes are not per price option. Breakfast, Lunch, Dinner, and plate size share the product recipe.
- Ingredients Required still follows the existing shortfall rule. A sale is not blocked when ingredients are short.
- `20261122_0134` was not applied to PostgreSQL.
- The acceptance executable was not rebuilt or launched for this change.
