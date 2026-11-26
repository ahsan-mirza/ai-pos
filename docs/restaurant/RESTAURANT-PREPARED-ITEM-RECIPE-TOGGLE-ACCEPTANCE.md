# Restaurant and cafe prepared-item toggle

Date: 22-11-2026

Status: **PASSED WITH LIMITATIONS**.

A restaurant or cafe made-to-order item has one product setting, **Sell without recipe / ingredient consumption**. Cashiers do not choose it at the till and cannot override it. This status is only the ingredient mode. Portion prices are in `RESTAURANT-PORTION-PRICING-ACCEPTANCE.md`. The live register walk is in `RESTAURANT-NATIVE-END-TO-END-ACCEPTANCE.md`. Recipe draw, shortfall, and the remaining checkout gaps are in `RESTAURANT-CAFE-RECIPE-CHECKOUT-OFFLINE-ACCEPTANCE.md`. Takeaway and delivery are in `RESTAURANT-TAKEAWAY-DELIVERY-OFFLINE-ACCEPTANCE.md`.

## Setting

`products.sell_without_recipe` is a boolean. Migration `20261122_0135_sell_without_recipe` adds it with `server_default` false. Existing rows stay false. An empty recipe is not treated as prepared, and the migration does not write stock movements. It was not applied to a protected database.

The register product form and the business portal product form show **Ingredient & Recipe Settings** for restaurant and cafe made-to-order items.

Toggle label: `Sell without recipe / ingredient consumption`.

Description: `Enable this for items that are already prepared or whose raw ingredients are managed separately. These items can be sold without recipe validation or raw-ingredient deduction.`

- On: the form says `Prepared item — no recipe consumption`.
- Off: the form says `Recipe required for POS sale`.
- New items start off. The form does not turn the toggle on by itself.
- Changing it on an existing item asks for confirmation. Past tickets, sales, and stock movements stay as they were.
- Only `portal:inventory_manage` can write the product. A cashier token received 403.

The flag is stored only when the business profile is `restaurant` or `cafe` and the item type is `MADE_TO_ORDER`. A pre-packaged item that sends the flag true is stored false. Grocery, electronics, fashion, and laundry are outside this rule. Quick service still uses the older cashier permission `pos:skip_recipe`.

## Toggle off

An active made-to-order item that is being created, activated, or explicitly saved with the toggle off must already have a recipe. The message is `A recipe is required for this product. Add its raw ingredients before saving.`

A brand-new item has no id yet, so it cannot own a recipe on the first save. The practical path is: save with the toggle on, add the recipe on Recipes, then turn the toggle off. A name-only edit of an older recipe-less dish does not start requiring a recipe. Sending the toggle off on that dish does.

The recipe editor stays on Recipes. Turning the toggle on does not delete the recipe. Portions share that one recipe. The model has no portion-specific ingredient quantities. A Full Plate and a Small Plate scale the same recipe by line quantity and yield.

The Business Pro menu item form keeps this toggle beside Pricing & Portions. A portion price change does not write a recipe or a stock movement. See `BUSINESS-PRO-RESTAURANT-CAFE-PORTION-PRICING-ACCEPTANCE.md`.

## Toggle on

New lines are stored with `skip_recipe` true. The sale does not validate ingredient availability, does not reserve ingredients, and does not write `RECIPE_OUT` or `recipe_usages`. The existing `recipe.skip` audit still records the line. Price, modifiers, tax, quantity, and the selected portion are unchanged.

A line that sends `skip_recipe` false for this item is rejected, including when the cashier is an administrator: `The ingredient requirement is set on the menu item. The till cannot change it.`

## Toggle off at the till

New lines must send `skip_recipe` false. `pos:skip_recipe` does not override the product. The sale then uses the existing `recipe_service.consume` path: draw `min(needed, available)`, write `RECIPE_OUT` and `recipe_usages`, and record `recipe.stock_short` when the draw is short. A shortfall still does not refuse the sale. That is the lifecycle this change kept. Adding the line to a cart or a table still does not move ingredient stock. Payment of an open order is the sale that consumes the recipe.

Dine-in, takeaway, delivery, and a direct sale use the same check. The open-order test stored a skipped line for a prepared item, sent it to the kitchen, and left ingredient stock unchanged. A later recipe-managed sale of the same dish drew the recipe. The earlier sale line stayed skipped.

## Offline

The register product cache adds `sell_without_recipe INTEGER NOT NULL DEFAULT 0`. A missing value stays false, so a recipe-managed item does not become prepared offline. New cart lines copy the cached flag into `skip_recipe`. The existing sale and open-order sync events carry that flag. There is no second queue, and the O5 and O6 contracts were not changed. A duplicate sale push does not add a second stock movement.

## Historical lines

`skip_recipe` on the sale, open order, and kitchen ticket remains the snapshot. Editing the product after the line exists does not rewrite it. Two lines that differ by portion or by that snapshot still do not merge.

## Tests

The disposable pytest database covered create rejection without a recipe, create with the toggle on and no recipe, a preserved recipe after the toggle moved both ways, cashier 403, a Full Plate sale with no ingredient movement, a rejected override, a later recipe draw of 10 from 100, an unchanged historical line, and a name-only edit of a recipe-less dish.

`node scripts/python.mjs -m pytest tests/test_menu_recipe_mode.py tests/test_recipes.py tests/test_menu.py -q --tb=line`

8 passed, 0 failed, exit 0.

`node scripts/python.mjs -m ruff check` on the edited API files exited 0 after the test import was wrapped.

Desktop and web `tsc --noEmit` exited 0. Desktop vitest on the form payload, portion payload, price dialog, and cart: 4 files, 34 tests, exit 0. `cargo check --offline` exit 0. `cargo test --offline --lib` with `POS_ENV=development`: 79 passed, exit 0, including the catalogue insert that writes the new product column and `skip_recipe_survives_save_and_reload`.

## Limitations

- The isolated restaurant register has since created Daal Channa, sold it with the toggle on, and parked that round on table T1. See `RESTAURANT-NATIVE-END-TO-END-ACCEPTANCE.md`. Recipe-managed sales, the cashier lockout, and the cafe register are still open on that walk.
- A short sale is still accepted. Unavailable ingredients are recorded, not used to refuse the sale.
- Portions do not have their own recipe quantities.
- A new active recipe-managed item cannot be saved until a recipe exists, and the recipe can be attached only after the product exists. The first save uses the toggle on, or the API returns 422.
- The product form points at Recipes. It does not embed the ingredient grid.
- A grocery tenant was not switched in this run. The guard was checked by sending the flag on a pre-packaged item, which stored false, and by applying the flag only for restaurant and cafe made-to-order items.
- Production data was not migrated or sold against.
