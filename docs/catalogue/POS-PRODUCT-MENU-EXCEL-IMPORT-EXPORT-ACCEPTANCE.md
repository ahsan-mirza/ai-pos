# Product and menu Excel import and export

Status: **PASSED WITH LIMITATIONS**

Workbook format version: **1**

Template file: `AxizPOS_Product_Menu_Import_Template.xlsx`

An export uses the same sheets and column names as the template. Re-importing an unchanged export updates nothing and does not create a second product or portion.

This was not deployed.

## Workbook

| Sheet | Role |
|---|---|
| Guide | Column meanings. Not imported. |
| Products | Grocery, electronics, fashion, laundry, and other non-menu products. Restaurant and cafe made-to-order items are not written here. |
| Menu Items | Made-to-order items when the store profile is restaurant, cafe, or quick service. |
| Menu Pricing Options | Portions for a menu item. |
| Modifiers | Modifier groups, options, and the products they are linked to. |
| `_AxizPOS` | Hidden metadata. Not a data sheet. |

Metadata keys: `format_version`, `template_version`, `exported_at`, `tenant` (store slug only), `business_profile`, `export_scope` (`all` or `filtered`). No passwords, tokens, or machine paths.

Prices are decimal text such as `3.00`. Yes/No is used for booleans. Empty optional cells stay empty.

There is no product description column. The product record does not have one.

## Products

Product ID, Product Name, SKU, Barcode, Product Type, Category, Sub-category, Brand, Unit, Base Price, Cost Price, Currency, Tax Category, Price Includes Tax, Active, Model Number, Open Price, Sold By Weight, PLU, Tare Grams, Minimum Age, Ingredient, Serialized, Season, Collection, Gender, Material, Fit, Care.

- Product ID blank creates a product. An exported id updates that product.
- SKU is required except on restaurant and cafe, where it may be blank. A stored SKU cannot be cleared or changed here.
- Barcode is required for a new product. An existing barcode cannot be changed here.
- Cost Price is exported and ignored on import. Stock is not in the workbook.
- Category, sub-category, brand, and unit must already exist. Import does not create them.
- Fashion columns are accepted only when the business profile id contains `fashion`. Otherwise a filled fashion cell is a row error.
- A modeled product cannot change category through this file. Item type cannot change while stock is on hand. The serialized flag cannot change on an existing product.

## Menu items

Product ID, Menu Item Name, SKU, Barcode, Category, Sub-category, Base Price, Currency, Tax Category, Price Includes Tax, Prepared Without Recipe, Active, Open Price.

SKU is optional for restaurant and cafe. Quick service still requires a SKU. Portions do not each need a SKU.

Prepared Without Recipe = Yes keeps `sell_without_recipe`. No keeps the recipe requirement. A new made-to-order item with No and no recipe is rejected. Import does not create recipes, ingredients, or consumption.

## Portions

Option ID, Product ID, Product Name, Option Name, Price, Currency, SKU, Active, Position.

The parent is the product id, or the menu item name when that name is unique in the file and the product id cell is blank. Option ID blank adds a portion. An exported option id updates that portion. Matching an existing portion name on the same product also updates it.

Rows that are not listed are left in place. Deactivate a portion with Active = No. Removing a portion stays on the menu screen.

After the merge, a menu item cannot be left with exactly one active portion. Zero portion rows leave the base price as it is.

Business Pro menu item editing and this workbook both write `menu_price_options`. The 26-11-2026 portion form did not change the sheet and did not re-run these workbook tests. Removing a portion stays on the menu form. See `docs/restaurant/BUSINESS-PRO-RESTAURANT-CAFE-PORTION-PRICING-ACCEPTANCE.md`.

## Modifiers

Product ID, Product Name, Group ID, Group Name, Min Select, Max Select, Group Active, Option ID, Option Name, Price Adjustment, Default, Option Active.

Groups and options match by id, then by name. Missing product links are added. Unlisted links are not removed. Link removal stays on the modifiers screen.

Grocery and other non-food profiles reject menu, portion, and modifier rows.

## Import modes

| Mode | Effect |
|---|---|
| Create new records only | Matching products and portions are reported and not written. |
| Update matching existing records | Unknown products are reported and not created. |
| Create new and update matching records | Creates and updates. |

Match order: exported Product ID, then unique SKU where that profile stores one, then unique barcode. The product name is not an update key. A unique name in the file can point a new portion at a new menu item.

Unchanged cells count as unchanged. Nothing is overwritten unless the mode and the preview both mark the row as an update.

## Validation and errors

Every row is checked before any write. One invalid row rejects the file. The error names the sheet, Excel row, field, and message. The same text can be downloaded as `AxizPOS_Product_Menu_Errors.xlsx`.

Checked: required name, profile SKU rule, barcode uniqueness, category and brand belonging to the store, sellable unit, numeric price with at most two decimal places, currency matching the store or the existing product, status, portion parent, duplicate portion, booleans, workbook version `1`, plain `.xlsx` under 10 MB and 2,000 data rows per sheet. Formulas, macros, and external links are refused.

## Write behavior

Confirm is required. The commit sends `Idempotency-Key`. The same key returns the stored summary and does not write again. The job id is the file hash; a different file after preview is refused.

The batch is one transaction. A conflict rolls back. A validation failure writes nothing. The audit row is `import.catalogue` and records the user, store, mode, version, and counts. Export uses the existing export audit.

Import does not change stock quantities, movements, allocations, sales, or recipe consumption. Catalogue changes still follow the existing product sync on save. Offline import and export stop with: "Import and export need a connection to the server. Nothing was changed." They are not added to the sale sync queue.

There is no background job. Files above the row or size cap are refused instead of queued.

## Permissions

`PORTAL_INVENTORY_MANAGE` is required on every workbook route. Cashiers do not receive it. The Products and Menu items screens show Import Excel, Export Excel, and Download template only for that permission. Add product and Add menu item stay as they were.

Export scope is the tenant catalogue the user can already read. Search text limits the export. The catalogue table has no row selection, so there is no checkbox export. Branch stock is not filtered and is not included.

## What was verified

API, from `apps/api`:

- `.\.venv\Scripts\python.exe -m ruff check app/services/catalogue_xlsx.py app/services/catalogue_workbook.py app/routers/v1/catalogue_workbook.py tests/test_catalogue_workbook.py` — exit 0
- `$env:APP_ENV='test'; .\.venv\Scripts\python.exe -m pytest tests/test_catalogue_workbook.py -q --tb=line` — 8 passed, exit 0

Those tests cover template version, export, re-import without duplicates, update by product id, a restaurant item with a blank SKU and three portions, row-specific errors that write nothing, missing portion parent, invalid file, unsupported version, formulas, cashier 403, unchanged stock, and idempotent retry.

Business Pro, from `apps/web`:

- `pnpm exec vitest run src/features/catalogue/workbook.test.ts` — 5 passed, exit 0
- `pnpm exec tsc -p tsconfig.json --noEmit` — exit 0

Register app, from `apps/desktop`:

- `pnpm exec vitest run src/features/inventory/workbook.test.ts` — 5 passed, exit 0
- `pnpm exec tsc -p tsconfig.json --noEmit` — exit 0

Register shell, from `apps/desktop/src-tauri`:

- `cargo test --lib retail::tests::only_retail_paths_pass -- --quiet` — 1 passed, exit 0

The full web and desktop Vitest suites were not re-run.

On the running cafe register preview (`http://localhost:1420/`, Menu items), Download template, Export Excel, and Import Excel sit beside Add menu item. Export showed "Exporting…" and then `Exported AxizPOS_Product_Menu_cafe_20261125-171529.xlsx.` The import wizard opened on Upload, with the six steps and the three modes, and Cancel closed it. Nothing was imported.

`http://127.0.0.1:5173` was not accepting connections, so the Business Pro products and modifiers screens were not clicked in the browser. Those screens use the same actions, gated by the same permission.

## Not done

The 15-step disposable-tenant walk was not run. No second export was re-imported on a live store. No screenshots were saved. Do not treat the cafe register check as that acceptance.

## Limitations

- No description field.
- Cost is export-only.
- SKU and barcode are not edited by this file.
- Variant matrices are not created or changed.
- Deleting a spreadsheet row does not delete a portion or a modifier link.
- Exactly one active portion is invalid.
- Import and export require the server.
- Maximum 2,000 data rows per sheet and 10 MB. There is no progress API beyond the wizard steps.
- Export follows the search box, not a specification filter or a checkbox selection.
- Pharmacy-only fields are not columns.
- Quick service can use the menu sheets, and SKU stays required.
- Preview is not stored on the server. Commit reads the file again and checks the hash.
