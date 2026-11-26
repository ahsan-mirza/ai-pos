# Business Pro restaurant and cafe portion pricing

Date: 26-11-2026

Status: **PASSED WITH LIMITATIONS**.

Restaurant and cafe menu items in Business Pro use the same product and `menu_price_options` records as AxizPOS Desktop. There is no second price table and no Business Pro-only pricing API.

This pass did not open a live Business Pro window or a register, and it did not capture the six screenshots in the request. Identity checks were made through the API. Production was not deployed, and no customer sale was settled.

## Contract reused

The register form already saves portions with `PUT /api/v1/menu/products/{product_id}/price-options` after the product create or update. Business Pro calls that same route.

| Form | Stored field |
|---|---|
| Base price | `products.price_cents` |
| Portion id | `menu_price_options.id` |
| Portion name | `menu_price_options.name` |
| Portion price | `menu_price_options.price_cents` |
| Active | `menu_price_options.is_active` |
| Order | `menu_price_options.position` |
| Optional portion SKU | `menu_price_options.sku`, left unset by the menu form |
| Prepared dish | `products.item_type = MADE_TO_ORDER` |
| Sell without recipe | `products.sell_without_recipe` |

A blank portion list keeps the single base price. Two or more named rows are portions of that one product. The register catalogue shows `From` and the lowest active portion price when at least two options are active. The cashier must pick one. The order line stores `price_option_id`, `price_option_name`, and `price_option_cents`. A later price edit does not rewrite that snapshot.

Prices use cents, at most two decimal places. Zero is allowed because `price_cents >= 0` is the existing rule. A negative price is rejected. Names are required, unique on the product without regard to case, and at least one option in a non-empty list must stay active. Exactly one active option is rejected. An empty list is the single-price path.

An option already used on a sale or an open order is deactivated instead of deleted. Unused options omitted from the save are deleted. Switching a multi-portion item back to a single price asks for confirmation, then sends an empty list. Historical lines keep their snapshots.

The product update and the portion replace remain two requests. Each commits on its own, which is the register's existing sequence. Catalogue changes for `menu_price_options` are written on that commit in the `menu` dataset with `kind: price_option`. The audit trail records `MenuPriceOption` create, update, and delete rows.

Tenant isolation is the existing row policy. An option id from another product returns 422, "A priced option does not belong to this item." A session scoped to another tenant cannot read or update the row.

`portal:inventory_manage` is required. A cashier PIN receives 403. Super Admin hardware-catalog screens are platform equipment, not tenant menu items, and were left unchanged.

## Business Pro form

For a restaurant or cafe tenant, Inventory → Menu items → Add menu item opens the product form.

**Pricing & Portions** has two modes:

- Single price. The price field is the selling price. The register does not ask for a portion.
- Multiple portions. Each row has a name, a price, an active flag, move up, move down, and remove. Add price option appends a row. Editing is in the row. Existing option ids are sent back.

Switching an existing single-price item to portions copies the current price into the first row so it is not dropped. The user still has to name at least two portions before save. Switching back to a single price asks for confirmation.

The base price stays on the product for reports that use one amount. In multiple-portion mode the field is labeled Base price.

SKU and barcode stay optional for restaurant and cafe. Auto Generate SKU stays optional. Portions do not each need a SKU. Grocery, electronics, fashion, and other profiles are unchanged.

The prepared-dish control and **Sell without recipe / ingredient consumption** stay on the same form and still write `sell_without_recipe`. Cashiers cannot change that flag. Portions share that one recipe. This form does not add per-portion ingredient quantities.

The menu list shows the base price for a single-price item and `From` plus the lowest active portion price for a multi-price item. The price cell expands to the active portion names. Filters are Single price, Multiple portions, Active, and Inactive. Search, category, brand, and pagination stay as they were. One product is one row.

The product drawer shows the same `From` price and the active portion names for a user who can view the catalog and cannot edit it.

The modifiers screen still has **Priced options**. It writes the same endpoint and uses the same payload rules.

Quick service is outside this form section. The register form and the priced-options panel still cover that profile.

## Excel

The standardized workbook already has a Menu Pricing Options sheet: option id, product id, name, price, active, and position. Business Pro import and export on the menu screen already call that workbook API. This pass did not re-run the workbook suite. The sheet was not changed. Unlisted portion rows are still left in place by import; removal stays on the menu form. See `docs/catalogue/POS-PRODUCT-MENU-EXCEL-IMPORT-EXPORT-ACCEPTANCE.md`.

## Tests

Business Pro, from `apps/web`:

`pnpm exec vitest run src/features/inventory/portionPricing.test.ts src/features/inventory/PricingPortionsFields.test.tsx src/features/inventory/ProductDetailDrawer.test.tsx --reporter=dot`

3 files, 18 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

The portion tests cover a single price, several portions, add, edit with the same id, deactivate, duplicate names, a blank name, an invalid price, a negative price, a zero price, a missing second price, a list with none active, optional absence of a portion SKU, keeping the current price when switching mode, reorder, and the `From` label.

API, from the repo root:

`node scripts/python.mjs -m pytest tests/test_menu.py tests/test_menu_recipe_mode.py tests/test_optional_menu_sku.py -q --tb=no`

9 passed, 0 failed, exit 0. About 9.7 seconds.

`node scripts/python.mjs -m pytest tests/test_menu.py::test_portion_prices_keep_identity_history_and_reject_bad_writes tests/test_tenant_scope.py::test_price_option_rows_stay_inside_their_tenant -q --tb=short`

2 passed, 0 failed, exit 0. About 2.8 seconds.

That API case creates Small Plate 300, Medium Plate 500, and Full Plate 900, then compares those option ids on the product list and on `GET /api/v1/menu/register`. It checks a catalogue change and a `MenuPriceOption` audit row for each id. It rejects a blank name, a negative price, a list with no active option, a single option, and an option id that belongs to another product. A zero price is accepted. A cashier PIN receives 403. A sale of Full Plate at 900 cents stays at 900 after Medium Plate moves to 550. Omitting Full Plate deactivates it and leaves the sale snapshot. An empty list leaves that sold option inactive and clears active portions from the product list.

`node scripts/python.mjs -m ruff check app/schemas/menu.py app/services/audit.py tests/test_menu.py tests/test_tenant_scope.py` exit 0.

`tests/test_tenant_scope.py::test_first_store_claims_migrated_roles_and_the_next_store_gets_its_own` failed in the same file with `assert 5 == 4` because five system roles exist, including Demo Explorer. That assertion was not part of this change.

Desktop, from `apps/desktop`:

`pnpm exec vitest run src/features/inventory/menuEntry.test.ts src/features/checkout/priceOptionModal.test.tsx --reporter=dot`

2 files, 6 tests, 0 failed, exit 0. The payload test keeps portion ids when a price is edited. The dialog test is the existing register selector.

`pnpm exec tsc -p tsconfig.json --noEmit` in `apps/desktop` exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` in `packages/shared-types` exit 0.

Rust tests were not run. Portion prices are not implemented in the Tauri crate.

The full web, desktop, and API suites were not run.

## Native acceptance

Not run. No disposable restaurant or cafe tenant was clicked through Business Pro and a register. No screenshots were captured. Synchronization is **not** marked passed as a live walk. The API test compared product and option ids, not only names and prices.

## Limitations

- Live Business Pro and register screens were not opened.
- Product save and portion save are two commits, matching the register. A portion failure after the product insert leaves the product in place; the form keeps the new id and the next save updates it.
- Zero portion prices remain valid.
- Quick service does not show Pricing & Portions on this form.
- Workbook import still does not delete unlisted portions.
- Portions share one recipe.
- The unrelated system-role count assertion in `test_tenant_scope.py` fails.
- Production data was not migrated or sold against.
