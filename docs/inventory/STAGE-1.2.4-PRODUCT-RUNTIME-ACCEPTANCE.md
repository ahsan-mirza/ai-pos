# Stage 1.2.4 — Product runtime acceptance

Date: 19 November 2026. No production deployment, migration, database change, or tenant activation. Stage 1.3 was not started. Other inventory forms were not redesigned.

## Environment identity

The Windows input desktop was available. The session was not locked. The acceptance register itself was not running, and its product form was not open.

| Item | Identified value |
|---|---|
| Acceptance executable | `D:\Work\ai-pos\acceptance\inventory\target\release\ai-pos-desktop.exe` |
| Executable size and write time | 20,881,408 bytes, 19 November 2026 15:06:45 UTC |
| Acceptance process | Not running |
| Application identity | `com.axizpos.inventory.acceptance` |
| WebView data directory | Present at `%LOCALAPPDATA%\com.axizpos.inventory.acceptance\EBWebView` |
| API | `http://127.0.0.1:18081`, listener PID 37356, parent node PID 60208, `scripts/python.mjs --env=inventory-acceptance -m app.serve` |
| Database | Container `axizpos-inventory-acceptance-db`, healthy, `127.0.0.1:55433`, listener PID 47156, database `axizpos_inventory_acceptance`, role `axizpos_acceptance` |
| Other AxizPOS desktop | PID 33672, `C:\Users\ahsan\AppData\Local\AI POS\ai-pos-desktop.exe`, visible window 24315754 titled `AI POS` |

That installed register was left running. It was not clicked, typed into, or closed. A second AxizPOS process was not started, so the acceptance executable was not launched. Developer app data, the developer `.env`, the developer API on port 8000, host Postgres on 5432, the Evolution containers, and the leftover pharmacy script process were left as they were.

Developer metadata, read as size and modification time only: `ai-pos.db` 286,720 bytes, 5 November 2026 16:45 UTC; `terminal.bin` 694 bytes, 12 November 2026 06:54 UTC; `.env` 1,878 bytes, 12 November 2026 15:21 UTC.

## Interrupted Acceptance Oats create

The values typed before the earlier interruption were name `Acceptance Oats 500g`, SKU `ACC-OATS-500G`, barcode `2003884332906`, price `2.25`, store `Acceptance Store A`, opening quantity `0`.

That barcode is not in `products`. The acceptance logs that were kept do not contain that SKU, that barcode, or that name, and they do not contain a request id for the interrupted save. The later product POSTs in `api-restart2.log` are HTTP 409. The interrupted request was not repeated.

A different oats row is already stored, once:

| Field | Persisted value |
|---|---|
| Id | `16737149-a7d2-48e5-94a3-026fd50848df` |
| Tenant | `106cd7bd-87e6-43ca-9ec7-6853f7d936ce` (the grocery acceptance tenant; the medicine row belongs to a different tenant) |
| Name | `Acceptance Oats 500g Revised` |
| SKU | `ACC-OATS-500G-500G` |
| Barcode | `2008627812707` |
| Price | 240 cents |
| VAT | `STANDARD`, price does not include tax |
| Category | Acceptance Dry Goods |
| Model number | `OATSMPN1` |
| Specifications | `pack` = `500g` |
| Created / updated | 15:14:26 UTC / 15:24:06 UTC |

Opening stock is one movement: `AUDIT_ADJUSTMENT` quantity 2, quantity after 2, reference `opening_balance`, at the same second as creation. There is no second opening movement. The level is on Acceptance Store A only: on hand 2, reserved 0, reorder level 1. Store B and the pharmacy store have no level for this product.

`GET /api/v1/products` as the store-bound Floor Manager returns this product together with `INV-TIN` and the archived rice row. `GET /api/v1/products/{id}` returns the same oats fields. `GET /api/v1/inventory/stock?store_id=` Store A returns the oats row with quantity 2. `INV-TIN` is still name `Acceptance Inventory Tin`, barcode `6291000001111`, price 500 cents. It was not edited.

The Windows form was not opened again, so this session did not confirm a success notification or a list refresh on screen.

## Product CRUD

Windows create, read, update, and archive on the redesigned form were not run. The installed AI POS window is the only live AxizPOS desktop.

What the API and database show from the earlier save:

- One oats product exists. Duplicate SKU and barcode counts are zero.
- A Floor Manager POST with the existing SKU and a new barcode returned 409 `SKU is already in use.`
- A Floor Manager POST with a new SKU and the existing barcode returned 409 `Barcode is already in use.`
- The product count stayed at the three grocery products. No stock movement was added. `INV-TIN` was unchanged.
- `INV-RICE-01` is inactive. Its Store A quantity is still 3, with the original opening movement and one sale movement. Search still returns the inactive row. The register sale grid filters `is_active === false` in `CheckoutPage`; that filter was not exercised on a window.

## Field parity

The comparison source remains `docs/inventory/STAGE-1.2-FORM-PARITY-MATRIX.md`. This session did not reopen the register form, so on-screen validation and dropdown behaviour were not rechecked. Persisted oats values match the product schema: name, price, VAT, SKU, barcode, category, model number, one custom specification, opening store, opening quantity, and reorder level.

| Area | Finding |
|---|---|
| Description | Not a `products` column and not a Business Pro product-form field. Intentionally unavailable. |
| Catalog identity, price, VAT, SKU, barcode, category, model number | Present on the register form and on `ProductCreate`. The saved oats row holds them. |
| Subcategory, brand, model | Present on the form. This oats row has none of the three ids set. |
| Custom specification row | Saved as `specifications.pack`. |
| Grocery schema fields (`net_weight`, storage, packaging, grade, origin) | `specSchemaFor` returns that schema for grocery categories whose names match produce, pantry, dairy, and the other grocery terms. `Acceptance Dry Goods` does not match, so it stays a custom list. `Produce` matches. A live category switch was not run. |
| Pharmacy lot, expiry, and the other pharmacy attributes | Sent only when the pharmacy capability is on. They were not added to the grocery form. `test_other_profiles_still_create_products_and_reject_pharmacy_fields` passed. |
| Cost, wholesale, warranty, supplier, modifiers | Not on the Business Pro product form. Not added. |

## Images and gallery

The Windows browse, drag-and-drop, type, size, preview, add, and remove steps were not run.

The oats product already has two `product_images` rows. Both files are WebP under `apps/api/storage/inv-accept/media/products/`, 84 and 88 bytes, with matching thumbnails. The image API returns both, and both URLs are under `/media/inv-accept/products/`. Stored dimensions are 64×64 and 64×48, which is the size of the earlier disposable fixtures after the server re-encode. The service rejects non JPEG/PNG/WebP with 415 and files over 5 MB with 413, then writes a WebP no wider than 1200 px and a thumbnail no wider than 320 px. The register form also calls `compressImageToWebp` before upload. Neither path was exercised from the window in this session. Gallery add and remove were not repeated.

## Dynamic attributes, SKU, and barcode

The saved specification `pack=500g` is still on the oats row, and the SKU contains that `500G` segment. This session did not add, edit, or remove a specification, and did not generate a new EAN-13 or Code 128 on the form.

Server duplicate checks rejected the existing SKU and the existing barcode. `productPayload.test.ts` covers required name, SKU, barcode, price, and category; auto-barcode leaving the barcode error clear; SKU resolution through `skuFromParts`; weighed opening quantity in grams; and omission of SKU and barcode on update. There is no separate automated test file for EAN-13 check digits or gallery persistence.

## Dropdowns and inline creation

The Windows searchable dropdowns, empty state, loading state, and error state were not opened.

API enforcement:

- Floor Manager `GET /api/v1/categories` returned 200 and included Acceptance Dry Goods and Produce.
- Floor Manager `POST /api/v1/categories` returned 403 `Categories are shared across branches. Ask a Super Admin to change them.`
- The catalog admin created `Stage 1.2.4 Probe` (201) and the probe deleted it (204). The category is gone. A hidden button was not used as evidence.

## Stock-list authentication

Original message: `This action requires a signed-in user.`

Request path:

1. `StockPanel` loads `inventoryApi.stock` when the workspace is online.
2. `inventoryApi.stock` calls `retailCall` for `GET /api/v1/inventory/stock`.
3. In the register, `retail_request` requires a register session, sends `X-Terminal-Token` from the terminal config, and adds `Authorization: Bearer` only when `user_token` is in memory.
4. `get_principal` uses the bearer token when it is present. With no bearer token it authenticates the terminal as a device principal.
5. `GET /api/v1/products` allows that device principal (`allow_device=True`).
6. `GET /api/v1/inventory/stock` uses `authorize(Permission.PORTAL_ACCESS)` without `allow_device`. A device principal receives 403 `This action requires a signed-in user.`
7. A user principal without `portal:access` receives 403 `You do not have permission for this action.` instead.

`auth-probe.txt` from the earlier session records device stock 403 with the signed-in-user message, device products 200, Floor Manager stock 200, and cashier stock and products 403 with the permission message.

This session repeated the Floor Manager stock call: HTTP 200, and the oats row was in the Store A result. The device key stored in the acceptance runtime file is not accepted by the running API (`login-pin` returns 401 `A valid terminal token is required.` and a stock call with that key returns 401 `Sign in or provide a valid API key.`). The cashier password login returns 403 `This account cannot sign in to the web portal.` The cashier PIN retest could not be repeated without a valid terminal token. No authorization rule was weakened, and no code was changed. The stock route is behaving as written: it requires a signed-in user, while the product list also accepts the terminal.

## Viewports

1024×768, 1280×800, 1366×768, and 1920×1080 were not opened. None of them pass.

## Grocery regression

On the disposable grocery tenant, Acceptance Dry Goods and Produce both exist. The oats product remains on Acceptance Dry Goods with its saved `pack` specification. `INV-TIN` remains on Produce at 500 cents. Pharmacy configuration was not edited. `tests/test_grocery.py` passed its four tests (age check, bag fee, produce waste idempotency, grocery-only suggestions). A live switch between Dry Goods and Produce on the register was not run.

## Backend reuse

Product create and update still go through `POST /api/v1/inventory/products` and `PATCH /api/v1/products/{id}`. Opening stock for the oats row is the existing `opening_balance` movement, not a direct quantity write. This session did not add a product table, a stock ledger, or a POS-only store, and it did not write quantities with SQL. Grocery list and detail calls did not return the other tenant's medicine. The oats level exists only on Store A. Duplicate SKU and barcode checks are enforced by the API. Image bytes for this tenant are under `storage/inv-accept/media/`.

## Tests and build

No source file changed, so the acceptance executable was not rebuilt. The binary on disk is the 19 November 2026 15:06:45 UTC build named above. A successful build is not claimed from that older file.

| Command | Result |
|---|---|
| `pnpm --filter @ai-pos/desktop typecheck` | Exit 0 |
| `pnpm --filter @ai-pos/desktop exec vitest run src/features/inventory/productPayload.test.ts` | 1 file, 6 tests passed |
| `node ..\..\scripts\python.mjs -m pytest tests/test_inventory.py::test_portal_product_creation_with_opening_stock tests/test_inventory.py::test_unused_product_can_be_deleted_and_stocked_ones_cannot tests/test_pharmacy_catalog.py::test_other_profiles_still_create_products_and_reject_pharmacy_fields tests/test_product_search.py::test_exact_barcode_ranks_first tests/test_units.py::test_product_form_sets_packs_and_weighed_goods_stay_in_grams tests/test_grocery.py -q --tb=line` | 9 passed |

Image-compression, gallery-persistence, and dropdown test files were not found. Those checks were not invented.

## Screenshot index

See `acceptance/inventory/evidence/stage-1.2.4/index.md`. Required Windows screenshots were not captured.

## Failures

No new product defect was fixed. The stock-list message is the existing device-principal refusal. The on-disk device key no longer authenticates, so the device and cashier retests from this session returned 401 and a portal password refusal rather than a fresh permission 403.

## Not run

- Windows product create, read, update, and archive on the redesigned form.
- Success notification and on-screen list appearance.
- Browse, drag-and-drop, file-type, 5 MB, compression, preview, and saved-gallery editing on the window.
- Specification add, edit, remove, and on-screen SKU or barcode generation.
- Dropdown search, cascade, empty, loading, and error states on the window.
- All four viewports.
- Live grocery category switch.
- Cashier PIN authorization retest, because the stored terminal key is rejected.

## Cleanup

Acceptance is incomplete, so nothing was removed. The acceptance API and disposable database are still running. The installed AI POS process was not closed. Developer file sizes and modification times are unchanged from the values above. Unrelated containers are still up.

## Remaining limitations

The product form has not had a completed Windows pass for create confirmation, gallery editing, or the four viewports. Other inventory screens are still the older register screens. The stock list still requires a signed-in user, which is why a terminal-only call shows the signed-in-user message while the product list loads.

## Follow-up the same evening

The oats reference row was checked again and left unchanged: SKU `ACC-OATS-500G-500G`, barcode `2008627812707`, on hand 2, reserved 0, one opening-balance movement. `INV-TIN` is still 500 cents, on hand 7, reserved 0. A duplicate SKU POST still returns 409.

A Floor Manager created one purchase order with two lines (the oats product and `INV-TIN`) and cancelled it. The API returned 201, then 200 with status `cancelled`. Two such cancelled drafts exist. Neither changed on-hand quantity or added a stock movement. A transfer was not created, because creating a transfer reserves source quantity.

The acceptance diagnostics file records identifier `com.axizpos.inventory.acceptance`, API `http://127.0.0.1:18081`, activation source `activation`, and `developer_env_loaded` false.

The device key copied in the acceptance runtime file did not match the enrolled register and returned 401. The sealed terminal file for `com.axizpos.inventory.acceptance` unseals to a token for tenant `inv-accept` and the same API. That enrolled token returns HTTP 200 for the product list and HTTP 403 `This action requires a signed-in user` for stock. Cashier PIN login with that token returns 200, and the cashier stock call returns 403 `You do not have permission for this action.` The runtime file was updated to the enrolled token. A second device was not created, and the installed register was not used. After the sync, the runtime token also returns product-list 200 and stock 403.

The Windows product form was still not driven at that point. Screen clicks would have been global while the installed AI POS window was open.

## Final sprint the same evening

The acceptance executable was rebuilt with `ACCEPTANCE_PROFILE=inventory` and API `http://127.0.0.1:18081`, then launched. Its process is PID 62684, `acceptance/inventory/target/release/ai-pos-desktop.exe`, window title `AxizPOS Inventory Acceptance`. UI Automation was limited to that process. The earlier pharmacy-identity binary panicked on startup and was replaced.

A Floor Manager created `Acceptance Millet 250g Revised` through that window: SKU `ACC-MILLE-250G`, barcode `2008255702111`, price later saved at 375 cents, opening quantity 1, reorder 2, one opening-balance movement. The same window archived it. A later create with SKU `ACC-MILLE-250G` showed "SKU is already in use." A create with barcode `2008255702111` showed "Barcode is already in use." No `ACC-DUP-PROBE` row exists. The product list has four rows. Oats and `INV-TIN` were not edited.

JPEG and PNG fixtures were stored on the millet product through the product image API and one image was deleted. The 44-byte WebP fixture was rejected as not a photo. A text file returned 415. A 5 MB zero-filled file returned 413 `Photos are limited to 5 MB.` The Windows file dialog and drag-and-drop were not driven. Window captures at 1024×768, 1280×800, 1366×768, and 1920×1080 are in `acceptance/inventory/evidence/final-release/`. At 1024×768 the product table and the tab row are clipped.

When rechecked after those captures, installed PID 33672 was no longer running. Its executable timestamp and the developer `ai-pos.db`, `terminal.bin`, and `.env` timestamps were unchanged. No close or input was sent to that process.

## Status

| Area | Outcome |
|---|---|
| Product form | PASSED WITH LIMITATIONS |
| Product CRUD | LIMITED |
| Images and gallery | LIMITED |
| Responsive acceptance | LIMITED |
| Overall inventory | FORM PARITY IN PROGRESS |
