# Stage 1.2 — Business Pro to Windows POS replication

Status: `FORM PARITY IN PROGRESS`

Business Pro (`apps/web`) is the source of truth. This note records what that product form actually does, what the Windows register (`apps/desktop`) now does with the same APIs, and what is still different. It is not a claim that every inventory form matches.

No production database was changed. No deployment was made. The running inventory acceptance executable was not rebuilt in this pass, so the window that was already open still has the older drawer.

## Source of truth

| Piece | Location |
|---|---|
| Product modal | `apps/web/src/features/inventory/ProductFormModal.tsx` |
| Pharmacy block | `apps/web/src/features/inventory/PharmacyFields.tsx` |
| Specification fields | `specSchemaFor` and `titleFromSpecs` in `packages/shared-types` |
| SKU and barcode | `packages/shared-types/src/productCodes.ts` (`skuFromParts`, `randomEan13`, `randomCode128`, `barcodeError`) |
| Searchable dropdown | `packages/ui/src/Select.tsx`, used by the portal `SelectField` |
| Photos | `ProductImageDropzone.tsx` (5 MB, 24 files, JPEG/PNG/WebP) and `PhotoGallery.tsx` |
| Image API | `POST /api/v1/inventory/products/{id}/images` and `apps/api/app/services/product_image_service.py` |
| Register form | `apps/desktop/src/features/inventory/productForm.tsx` |
| Register lookups | `apps/desktop/src/features/inventory/creatableLookup.tsx` |
| Register photos | `apps/desktop/src/features/inventory/productPhotos.tsx` |
| Register shell upload | `retail_upload` in `apps/desktop/src-tauri/src/retail.rs` |

The portal “tabs” are section jumps. Catalog, Specifications, Product, and Stock stay mounted, so values survive a section change. The register uses the same pattern inside `FormModal`.

## Modal

`FormModal` is a white surface, `h-[96vh] w-[96vw] max-w-6xl`, `rounded-3xl`, on a `bg-[#1A191D]/60` overlay. The heading is `New product` or `Edit ${product.name}`. The create subtitle is `Products are shared by every branch; stock is per branch.` The edit subtitle is the SKU and barcode. Cancel and Create product / Save changes stay in the footer. The body scrolls.

## Catalog

Photos: drop or browse, JPEG, PNG, or WebP, 5 MB each, at most 24. The chosen main photo is uploaded first. The catalogue image service stores the file. The register does not compress to WebP before upload. Business Pro does. The register shows an existing `image_url` as a thumbnail and does not reorder, replace, or delete photos that are already saved.

Placement:

- Category. Searchable. Inline create only for a catalog admin: inventory manage, and the user is not bound to one store. `POST /api/v1/categories` with `{ name }`. The new id is selected. Sub-category, model, and specifications clear.
- Sub-category. Options follow the category. Changing the category clears an incompatible sub-category. Inline create is `POST /api/v1/categories/{id}/sub-categories`.
- Brand. Searchable. Inline create requires a sub-category and sends `sub_category_ids`.
- Model. Disabled until brand and sub-category are set. Hint: pick a sub-category and brand first. Inline create sends `brand_id` and `sub_category_id`.

Gender and VAT stay controlled lists. They are not creatable records.

## Specifications

`specSchemaFor` chooses the fields from the category. The register uses `SpecEditor` and the same searchable specification control. A category or sub-category change clears specifications, which is what Business Pro does.

`Auto-Generate Name & SKU from Specs` calls `titleFromSpecs`, then `skuFromParts(prefix, title, {})` when the product is new, and marks the SKU manual so a later keystroke does not overwrite it. Edit mode does not rewrite the SKU.

When the fashion capability is on and the schema has variant keys, `FashionMatrix` is shown. Included rows are posted to `POST /api/v1/product-models/{id}/matrix`. If there is no model yet, the form creates one from the brand and sub-category first. This path has not been run on a fashion tenant.

## Product

Name, price (`price_cents`, two decimal places), tax-inclusive flag, SKU, barcode, manufacturer part number, VAT (`STANDARD`, `ZERO`, `EXEMPT`), season, collection, gender, open price, minimum age, packs, and the serial toggle follow the portal conditions.

SKU: prefix up to the shared cleaner, Auto Generate, live generation until the user edits it, fixed after create.

Barcode: prefix state defaults to `200` in both forms. It is not read from a settings record in the form. EAN-13 and Code 128 use `randomEan13` and `randomCode128`. Auto-assign is on by default. A blank barcode is allowed only while that toggle is on. Generation searches products and retries up to six times. The barcode is fixed after create.

Open price, weight, PLU, tare, packs, and serial tracking stay mutually exclusive the way the portal form already enforced. Serial tracking is not offered for pharmacy. Opening quantity for a serialized item stays 0. Serialized stock is still received through the existing purchase-order path.

## Stock

Products are shared. Opening quantity and minimum reorder are for one store. A store-bound user is locked to that store. Opening quantity goes through the product create payload and the stock movement service. The register does not write a quantity into SQLite.

## Permissions

Inline category, sub-category, brand, and model creation uses the same gate as Business Pro: portal inventory manage, and no store id. Backend authorization stays authoritative. A store-bound user can search and select.

## Checks in this pass

- `npx tsc -p tsconfig.json --noEmit` in `apps/desktop` completed with no errors.
- `vitest` on `productPayload.test.ts` and `tabs.test.ts`: 12 tests passed.
- The earlier grocery acceptance (create, edit price, empty submit, duplicate SKU, duplicate barcode, archive) still stands for the older drawer.
- Stage 1.2.3 rebuilt and launched `acceptance/inventory/target/release/ai-pos-desktop.exe`. Diagnostics recorded identifier `com.axizpos.inventory.acceptance`, API `http://127.0.0.1:18081`, and `developer_env_loaded` false. The new modal, category search, SKU `ACC-OATS-500G`, and barcode `2003884332906` were visible. Create, photos, gallery, viewports, and fashion were not finished. The Windows session locked with the form still open.
- Viewports 1024×768, 1280×800, 1366×768, and 1920×1080 were not rechecked.

## Still different

1. Category, brand, model, unit, pricing, price list, price change, stock adjustment, purchase order, goods receiving, transfer, stock count, batch, replenishment, and IMEI screens are the existing register forms. Purchase orders and transfers are still one product per document.
2. Photo compression and saved-gallery editing are in this build and were not exercised on a saved product.
3. The fashion matrix save is in the form and has not been exercised on a fashion tenant.
4. The rebuilt window showed the new product form. A completed create on that window was not recorded before the session locked.

`PRODUCT FORM PARITY COMPLETE` and `INVENTORY FORM PARITY COMPLETE` are not claimed.
