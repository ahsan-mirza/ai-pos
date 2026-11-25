# Restaurant and cafe recipe, checkout, and offline closure

Date: 23-11-2026

Continues `RESTAURANT-NATIVE-END-TO-END-ACCEPTANCE.md` on the same disposable restaurant database. The register process `45596` was no longer running. The same executable was started again. The database, tenant, cashier, and API were not recreated.

## Environment reused

| Item | Value |
|---|---|
| Identifier | `com.axizpos.restaurant.portion` |
| Executable | `apps/desktop/src-tauri/target/portion-restaurant/ai-pos-desktop.exe` |
| SHA-256 | `874E37D84516FD3EC026DE355C5B8410CF28690521B94AFD108A70A0C813C71B` |
| Process after relaunch | PID 48928, HWND 327842 |
| API | `http://127.0.0.1:18094`, health `{"status":"ok"}` |
| Database | `%TEMP%\axiz-portion\restaurant\axizpos_portion_restaurant.sqlite` |
| Schema | `create_all`. Alembic `20261122_0135` was not applied. |
| Laundry till | PID 1908, left running |

Opening stock movement `8c09f21ceaeb4942a87042723b59c8e5` is still the Channa `AUDIT_ADJUSTMENT` of 100. It was not rewritten.

## Workstreams

| # | Workstream | Status |
|---|---|---|
| 1 | Product first-save and recipe configuration | PASSED WITH LIMITATIONS |
| 2 | Recipe-required validation | PASSED |
| 3 | Prepared-item checkout | PASSED WITH LIMITATIONS |
| 4 | Recipe-managed consumption | PASSED |
| 5 | Ingredient shortfall | PASSED |
| 6 | Cashier permissions and legacy skip permission | PASSED WITH LIMITATIONS |
| 7 | Takeaway | PASSED WITH LIMITATIONS |
| 8 | Delivery | PASSED WITH LIMITATIONS |
| 9 | Direct checkout | PASSED |
| 10 | Restart persistence | PASSED WITH LIMITATIONS |
| 11 | Offline replay | NOT RUN |
| 12 | Cafe native acceptance | NOT RUN |

Takeaway, delivery, and the 25-11-2026 reopen are in `RESTAURANT-TAKEAWAY-DELIVERY-OFFLINE-ACCEPTANCE.md`.

The combined Restaurant/Cafe workflow stays **IN PROGRESS**.

## 1. First-save recipe workflow — PASSED WITH LIMITATIONS

Chicken Karahi was created on the register as one made-to-order item, sell-without-recipe on, base price AED 6.00. Portions Half AED 6.00 and Full AED 11.00 are on that same product. Plain Roti was not created.

The register Recipes tab lists `Chicken Karahi` / `Channa: 2`. That panel does not edit recipe lines. The recipe was saved through the existing `PUT /api/v1/recipes/{product_id}` used by the portal: yield 1, Channa quantity 2. The product was then reopened on the register, the toggle was turned off, and Save changes stored `sell_without_recipe = 0`. The recipe row and its one line remained.

## 2. Recipe-required validation — PASSED

A new Plain Roti, category Kitchen, price AED 1.00, toggle left off, was submitted from Product Entry. The form stayed open and showed:

`A recipe is required for this product. Add its raw ingredients before saving.`

The products table still contains only Channa, Chicken Karahi, Daal Channa, and Mineral Water.

## 3. Prepared-item checkout — PASSED WITH LIMITATIONS

The earlier unpaid T1 round is unchanged: Small Plate 300, Full Plate 900, Mineral Water 200, each `skip_recipe = 1`. No new stock movement was created for those lines. Channa on hand moved only when Chicken Karahi was sold.

The stock gate still skips finished-goods checks only when `sell_without_recipe`, `has_recipe`, `item_type` made-to-order, or an untracked/service/open-price flag applies. A tracked item without those flags still uses the quantity check.

## 4. Recipe-managed consumption — PASSED

Recipe consumption runs when the sale is recorded, not when a table round is sent.

Direct cash sale `PORTIONR-PR1-000001`: Chicken Karahi Half, quantity 1, 600 cents, `skip_recipe = 0`.

`recipe_usages`: needed 2, drawn 2. Movement `c5f0e4193d87441381304d22ff4c7442`, type `RECIPE_OUT`, quantity -2, quantity after 98, reference `sale_recipe`. Reserved quantity stayed 0. The opening movement id did not change.

## 5. Ingredient shortfall — PASSED

Direct cash sale `PORTIONR-PR1-000002`: Chicken Karahi Full, quantity 50, 1100 cents, `skip_recipe = 0`. The portion does not change the recipe. Need was 100 pieces.

`recipe_usages`: needed 100, drawn 98. Movement `591432493cc8493bbd22a58bd0d9de19`, `RECIPE_OUT`, quantity -98, quantity after 0. Audit `recipe.stock_short` records short 2 for Channa. On hand is 0 and reserved is 0. The sale was recorded. No stock was invented to cover the gap.

## 6. Permissions — PASSED WITH LIMITATIONS

Cashier `portioncashier`, pos scope:

- `PATCH` of `sell_without_recipe` returned 403, missing `portal:inventory_manage`.
- `PUT` of the recipe returned 403, missing `portal:inventory_manage`.
- The product flag stayed 0 and the recipe line count stayed 1.

The seeded Cashier role does not include `pos:skip_recipe`. Portion Owner is Super Admin and therefore has that permission. With the owner pos token, adding Chicken Karahi to T1 with `skip_recipe` true returned 422 `ingredient_mode`: `The ingredient requirement is set on the menu item. The till cannot change it.` Forcing Daal Channa to `skip_recipe` false returned the same refusal. T1 stayed at 3 lines. The register user was not switched to the cashier screen.

## 7. Takeaway — IN PROGRESS

The takeaway pane is open. The cart holds Mineral Water, `Ingredients not required`, AED 2.00, and Chicken Karahi Half, AED 6.00. Send round shows `Choose a table or guest before sending to the kitchen.` The Start takeaway control did not create an order. Stock movements stayed at 3 and on hand stayed 0.

## 8. Delivery — NOT RUN

## 9. Direct checkout — PASSED

Both recipe sales above were cash on this register, exact tender, change AED 0.00. No card terminal was used. Prepared-item direct checkout was already covered by the earlier T1 round, which was not charged.

## 10. Restart persistence — PASSED WITH LIMITATIONS

After the same executable was started as PID 48928, Portion Owner was signed in, the catalogue showed Chicken Karahi `From AED 6.00`, Daal Channa `From AED 3.00`, and Mineral Water AED 2.00, and T1 was still the open dine-in order in the database. The sent T1 lines were not opened again on screen in this pass.

## 11. Offline replay — NOT RUN

The disposable API was left up so the recipe sales could be recorded.

## 12. Cafe — NOT RUN

The cafe acceptance build exists and was not started. The restaurant register and the laundry till were not retargeted.

## Automated checks

`node scripts/python.mjs -m pytest tests/test_menu_recipe_mode.py tests/test_recipes.py tests/test_menu.py -q`

9 passed in 10.35s, exit 0.

No Rust or desktop TypeScript files changed in this pass. `cargo check` and the desktop typecheck were not rerun.

## Screenshots

`docs/restaurant/evidence/native/recipes-chicken-karahi.webp`

`docs/restaurant/evidence/native/cart-karahi-half.webp`

`docs/restaurant/evidence/native/cash-sale-recorded.webp`

`docs/restaurant/evidence/native/cart-karahi-full-50.webp`

`docs/restaurant/evidence/native/takeaway-cart.webp`

## Next phase

Finish takeaway and delivery on this same register, reopen T1 on screen, run offline replay without resetting the database, then start the separate cafe acceptance build. Do not deploy.
