# Restaurant native portion and prepared-item acceptance

Date: 22-11-2026

The continuation, including recipe draw and the remaining gaps, is in `RESTAURANT-CAFE-RECIPE-CHECKOUT-OFFLINE-ACCEPTANCE.md`. Takeaway and delivery reopen evidence is in `RESTAURANT-TAKEAWAY-DELIVERY-OFFLINE-ACCEPTANCE.md`.

This is the live Windows register walk for portion pricing and the product-level prepared-item setting. API and mocked UI results stay in `RESTAURANT-PORTION-PRICING-ACCEPTANCE.md` and `RESTAURANT-PREPARED-ITEM-RECIPE-TOGGLE-ACCEPTANCE.md`. They are not treated as native acceptance.

## Status

### A. Portion pricing — PASSED WITH LIMITATIONS

On the isolated restaurant register, Product Entry stored three portions on one Daal Channa item, the catalogue showed `From AED 3.00`, the portion dialog required a choice, Small Plate and Full Plate became separate cart lines, a repeated Small Plate increased that line, Cancel left the cart unchanged, and a single-price Mineral Water at AED 2.00 added through the quantity dialog with no portion. Those lines were sent on unpaid dine-in table T1 and stored with the option id, name, and price.

Still open: takeaway, delivery, direct checkout, restart, a later price edit against the saved lines, and the cafe register.

### B. Prepared-item / recipe toggle — IN PROGRESS

Daal Channa and Mineral Water were saved with `sell_without_recipe` on, sold onto T1 with `skip_recipe` 1, and created no raw-material movement. A cart defect that blocked that add was fixed and rebuilt into the acceptance app.

Still open: the documented first-save recipe workflow, the recipe-required validation message, a prepared item that keeps an existing recipe, recipe-managed stock draw, shortfall recording, and cashier restrictions.

### C. Combined Restaurant/Cafe workflow — IN PROGRESS

Portion selection and prepared-item sales work together on one unpaid dine-in round. The recipe-managed half, the other service modes, offline replay, and the cafe register are not done.

## Environment

| Item | Value |
|---|---|
| Profile | Restaurant, disposable |
| Identifier | `com.axizpos.restaurant.portion` |
| Window title | AxizPOS Restaurant Portion |
| Executable | `apps/desktop/src-tauri/target/portion-restaurant/ai-pos-desktop.exe` |
| SHA-256 | `874E37D84516FD3EC026DE355C5B8410CF28690521B94AFD108A70A0C813C71B` |
| Process | PID 45596, HWND 6032820 |
| API | `http://127.0.0.1:18094` |
| API database | `%TEMP%\axiz-portion\restaurant\axizpos_portion_restaurant.sqlite` |
| Register data | `%APPDATA%\com.axizpos.restaurant.portion` |
| Register SQLite | `%APPDATA%\com.axizpos.restaurant.portion\tenants\portionr\ai-pos.db` |
| Store | Portion Restaurant, code `portionr`, currency AED |
| Signed-in user | Portion Owner, Super Admin |
| Build | `POS_ENV=acceptance`, `ACCEPTANCE_PROFILE=portion-restaurant` |

The schema on this database comes from `Base.metadata.create_all`. Alembic revision `20261122_0135` was not executed. `products.sell_without_recipe` is present. The laundry till (PID 1908, release executable) was left running. The older restaurant acceptance register on port 18089 was not used. No production database was migrated or sold against.

The cafe acceptance binary was built earlier and was not started. Cafe is not blocked. It has not been tested.

The footer chip reads ACTIVATED / OFFLINE. Product saves, catalogue reloads, and the table round still reached the API on port 18094. The chip is recorded and was not treated as a save failure.

## Defect fixed during this walk

A prepared dish with `sell_without_recipe` and no finished-goods stock could not be added. The register catalogue stores the flag and `has_recipe`, and it does not store `item_type`. The cart treated Daal Channa as a tracked SKU with quantity 0 and refused the line. The quantity dialog showed `That quantity could not be added.`

`stockError`, the offline allocation check, and the catalogue card now treat `sell_without_recipe` the same way they already treat a recipe dish: no finished-goods stock gate and no out-of-stock treatment. The acceptance executable above includes that fix.

Two earlier register defects were already required for portion save and remain in this build:

- The register request whitelist now allows `/api/v1/menu/products`, so the till can save portion prices. Modifier groups and combos stay blocked.
- Portion list and replace accept the till's pos-scoped inventory token. Modifier and combo writes stay portal-only.

## Native evidence

Screenshots are in `docs/restaurant/evidence/native/`.

### Product entry

Menu items on the register, after both saves:

- Channa, raw ingredient, AED 0.00, barcode `281000000001`
- Daal Channa, one row, SKU `DAA-CHANN`, barcode `2009572294563`, AED 3.00, active
- Mineral Water, one row, SKU `MIN-WATER`, barcode `2001284411535`, AED 2.00, active

Daal Channa is `MADE_TO_ORDER`, `sell_without_recipe` 1, and has no recipe. Its portions are one product:

| Portion | Cents | Option id |
|---|---:|---|
| Small Plate | 300 | `497ee79877ad448e83ec795c1f95b80c` |
| Medium Plate | 500 | `ae6a7f4948124769af1e57b3686ed654` |
| Full Plate | 900 | `5fe3948e47d54848b1b302cdb25a59af` |

Mineral Water is a single-price prepared dish at 200 cents, `sell_without_recipe` 1, with no portion rows. The opening-stock branch list on that form showed `No branch yet`, so it was saved as a prepared dish rather than a stocked pre-packaged bottle.

### Catalogue and portion dialog

The checkout card shows `From AED 3.00` for Daal Channa and `AED 2.00` for Mineral Water.

The Daal Channa dialog title is the product name. The prompt is `Choose portion and quantity.` The choices are Small Plate AED 3.00, Medium Plate AED 5.00, and Full Plate AED 9.00. Nothing is selected at open. Unit price and total stay blank, and Add stays disabled, until a portion is chosen. After Small Plate, the dialog shows unit price AED 3.00, total AED 3.00, and `Add 1 × Small Plate — AED 3.00`.

Cancel from an unselected dialog left the cart empty. A later Cancel, after lines existed, left those lines unchanged.

### Cart

After Small Plate, Full Plate, and a second Small Plate:

- Small Plate, quantity 2, AED 6.00, `Ingredients not required`
- Full Plate, quantity 1, AED 9.00, `Ingredients not required`
- Subtotal AED 15.00, tax AED 0.75, pay AED 15.75

The repeat increased the Small Plate line. It did not add a third line.

Mineral Water opens `How many are you selling?` with unit price AED 2.00 and Add already enabled. It does not ask for a portion. The line joins the cart as Mineral Water, AED 2.00, `Ingredients not required`.

### Unpaid dine-in round

Table T1 in Main Room was seated for 2. The round sent to the kitchen was Small Plate, Full Plate, and Mineral Water. The register reported `Round sent to the kitchen. The table stays open for the next round.` The cart for the next round was empty. No payment was taken. `sales` count is 0.

`open_orders` row: service `DINE_IN`, status `OPEN`, name `T1`, covers 2, number 1.

`open_order_items`:

| Line | Option id | Name | Unit cents | Quantity | skip_recipe |
|---|---|---|---:|---:|---:|
| Daal Channa | `497ee79877ad448e83ec795c1f95b80c` | Small Plate | 300 | 1 | 1 |
| Daal Channa | `5fe3948e47d54848b1b302cdb25a59af` | Full Plate | 900 | 1 | 1 |
| Mineral Water | none | none | 200 | 1 | 1 |

The option ids match `menu_price_options`.

### Stock

`stock_movements` has one row: Channa opening balance, quantity 100, `AUDIT_ADJUSTMENT`, note `Opening stock`, created before the table round. The prepared round added no movement. Channa on hand stayed 100. `recipes` count is 0.

## Automated checks this walk

`node scripts/python.mjs -m pytest tests/test_menu_recipe_mode.py tests/test_recipes.py tests/test_menu.py -q`

9 passed, exit 0. The extra test is `test_register_pin_can_save_portion_prices`.

Desktop vitest:

- `cart.test.ts`, `productPayload.test.ts`, `priceOptionModal.test.tsx`: 31 passed, exit 0. Includes `adds a prepared dish that has no finished-goods stock`.
- `menuEntry.test.ts`: 4 passed, exit 0.
- `cataloguePreference.test.ts` and `catalogProfileAcceptance.test.tsx` were included in an earlier 41-test run that also passed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` in `apps/desktop`: exit 0.

`cargo check --offline` in `apps/desktop/src-tauri` with `POS_ENV=development`: finished, exit 0. Web `tsc` was not rerun. The TypeScript change is in the desktop cart, allocation check, and catalogue card.

Rust `retail::tests` from the whitelist change: 4 passed, exit 0, with `POS_ENV=development`. The full library suite was not rerun for the TypeScript stock fix.

## Explicitly untested

- Cafe register, port 18095, identifier `com.axizpos.cafe.portion`.
- Recipe-managed item, first-save workflow, and the message `A recipe is required for this product. Add its raw ingredients before saving.`
- A prepared item that still has a recipe, and confirmation that the recipe stays saved.
- Ingredient shortfall recording on a real sale.
- Cashier UI and API: cannot change the product setting, cannot skip at checkout, cannot edit the recipe.
- Takeaway, delivery, and direct checkout.
- Restart the register and reopen the unpaid ticket on screen. The API row is saved. Recall opened held sales and showed `No sales on hold.` The sent round is the open table order, not a held sale.
- Edit the menu price or the toggle and confirm historical lines stay unchanged.
- Offline disconnect, restart, reconnect, and duplicate protection.
- Grocery, electronics, fashion, laundry, and quick service on this walk. Those profiles were not launched. The laundry till was not used.

## Known limitations, unchanged

- A new menu item cannot own a recipe on its first save. The supported path is to save it prepared, add the recipe, then turn the toggle off.
- All portions share one recipe. Separate ingredient quantities for Small, Medium, and Full are a future enhancement.
- A recipe shortfall is recorded and the sale is not refused.
- Older recipe-less products stay as they are until someone edits them. This disposable database had no legacy catalogue.

## Next phase

Finish the recipe-managed half on this same disposable restaurant register: first-save workflow, validation message, recipe draw, shortfall, and cashier restrictions. Then cover takeaway, delivery, direct checkout, restart, offline replay, and the cafe register. Do not deploy.
