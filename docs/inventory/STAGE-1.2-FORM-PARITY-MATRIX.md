# Stage 1.2 form parity matrix

Business Pro (`apps/web/src/features/inventory/ProductFormModal.tsx` and `PharmacyFields.tsx`) is the reference. The Windows register product form is `apps/desktop/src/features/inventory/productForm.tsx`, rendered in `FormModal` (96vw by 96vh, maximum width `max-w-6xl`). Both save through `POST /api/v1/inventory/products` and `PATCH /api/v1/products/{id}`, including a nested `pharmacy` object when the pharmacy capability is on.

This matrix is from those forms and `ProductCreate` / `ProductUpdate`, then checked against the running inventory register (`com.axizpos.inventory.acceptance`, grocery, Store A) and a read-only look at the live Business Pro product form. Status `FORM PARITY IN PROGRESS`. Complete parity is not claimed.

The register product form uses the same `@ai-pos/ui` `Select` as Business Pro, through `CreatableLookupField`. Inline create is offered only to a tenant catalog admin (`portal` inventory manage and no store binding). A store-bound manager can search and select, and cannot add a category from the product form.

Stage 1.2.3 rebuilt `acceptance/inventory/target/release/ai-pos-desktop.exe` (19 Nov 2026, 18:45) with identity `com.axizpos.inventory.acceptance` and API `http://127.0.0.1:18081`. On that window, signed in as the store-bound Floor Manager, the new product modal showed Catalog, Specifications, Product, and Stock jumps, a photo drop zone (JPEG, PNG, WebP, 5 MB), a searchable category list, and a fixed Cancel / Create product footer. Typing `dry` left only Acceptance Dry Goods and no Add action. Selecting that category, then jumping to Product, kept the category. The name Acceptance Oats 500g produced SKU `ACC-OATS-500G`. A save attempt filled barcode `2003884332906` (prefix 200) and left the form open. The Windows session locked before the create result, photo upload, gallery edit, viewport sizes, and a fashion-tenant matrix could be confirmed. The Stock list once showed “This action requires a signed-in user” while the product list still loaded.

Statuses: MATCHED, MISSING IN POS, DIFFERENT VALIDATION, DIFFERENT DEFAULT, DIFFERENT BEHAVIOUR, NOT APPLICABLE.

## Product — catalog, identity, price, stock

| Form | Field | Business Pro | Windows POS | Validation | Status |
|---|---|---|---|---|---|
| Product | Name | Present | Present | Required | MATCHED |
| Product | Price / price per kg | Present | Present | Up to two decimal places, stored as `price_cents` | MATCHED |
| Product | Price includes tax | Present | Present | Defaults off | MATCHED |
| Product | SKU | Present, editable until first save | Present, disabled on edit | Required on create. Unique on the server | MATCHED |
| Product | SKU prefix and auto-generate | Present. `skuFromParts` in shared types | Present. Same function. Manual edit stops the live update | Unique on the server | MATCHED |
| Product | Barcode / UPC / EAN | Present, fixed after create | Present, disabled on edit | Required on create | MATCHED |
| Product | Auto-assign barcode, EAN-13, Code 128, barcode prefix | Present. Prefix defaults to 200 and is editable | Present. Same `randomEan13` and `randomCode128`. Uniqueness is checked with product search | Blank is allowed only while auto-assign is on | MATCHED |
| Product | Manufacturer part number | Present | Present | Optional | MATCHED |
| Product | VAT treatment | Present | Present | STANDARD, ZERO, EXEMPT. Default STANDARD | MATCHED |
| Product | Category | Present | Present | Category or model required, including pharmacy | MATCHED |
| Product | Sub-category | Present | Present | Options follow the category. Cleared when the category changes | MATCHED |
| Product | Brand | Present | Present | Optional | MATCHED |
| Product | Model | Present | Present | Enabled after brand and sub-category. Filtered by both | MATCHED |
| Product | Season, collection, gender | Present for fashion when no model is chosen | Present on the same condition | Optional. Not sent when a model is selected | MATCHED |
| Product | Material, fit, care | On the API type only. The portal form does not edit them | Not shown | Sending them would clear values the portal never edits | NOT APPLICABLE |
| Product | Open price | Present when not weighed or serialized | Present on the same condition | Cannot combine with weight or serial tracking | MATCHED |
| Product | Sold by weight | Present when the weighed capability is on | Present on the same condition | Not with serial or open price | MATCHED |
| Product | Scale PLU | Present when weighed | Present when weighed | Empty, or 4–6 digits, and only when weighed | MATCHED |
| Product | Tare grams | Present when weighed | Present when weighed | Whole grams. Default 0 | MATCHED |
| Product | Minimum age | Present | Present | Blank, or a whole number from 1 to 120 | MATCHED |
| Product | Item type | Present for restaurant, cafe, and quick service | Present on the same profiles | Prepared dish, raw ingredient, or pre-packaged | MATCHED |
| Product | Ingredient | Present when recipes are on and the profile is not food service | Present on the same condition | A raw food-service item is sent as an ingredient | MATCHED |
| Product | Sells in (packs) | Present | Present | Piece is always included. Packs are hidden for weighed, serialized, and open-price items | MATCHED |
| Product | Track IMEI / serial | Present on create when serial tracking is on | Present on create on the same condition | Opening quantity must be 0. Not offered for pharmacy | MATCHED |
| Product | Opening stock store | Present on create | Present on create | Required when opening quantity is above 0. Locked to the signed-in store | MATCHED |
| Product | Opening quantity / kg | Present on create | Present on create | Whole units, or kilograms to three decimals. Kilograms are stored as grams | MATCHED |
| Product | Min reorder level | Present on create | Present on create | Whole number | MATCHED |
| Product | Active | Present on edit | Present on edit | Unchecking archives. Past sales stay. The register will not sell it | MATCHED |
| Product | Product image | Drag and drop, browse, compress to WebP, JPEG/PNG/WebP, 5 MB, 24 photos, main photo uploaded first, saved gallery | Drop or browse, preview, main, remove, then `POST /api/v1/inventory/products/{id}/images` through `retail_upload`. Existing photo is a thumbnail | The register does not compress before upload and does not edit the saved gallery. Not rebuilt into the acceptance executable | DIFFERENT BEHAVIOUR |
| Product | Category specification fields | Present from `specSchemaFor` | Present from the same function | Variant keys are also saved on `variant_attributes` | MATCHED |
| Product | Fashion variant matrix | Present. Saves through the model matrix API | Present when the fashion capability and a fashion schema are on. Included rows call the same matrix API | Not exercised on a fashion tenant | DIFFERENT BEHAVIOUR |
| Product | Delete if unused | Supported by the product API | Present for a non-pharmacy manager | Server returns 409 when sales, movements, or lots still reference it | MATCHED |

## Product — profile-specific fields

These appear only when the category schema or the pharmacy capability says so. The drawer does not invent a field the portal form omits.

| Form | Field | Business Pro | Windows POS | Validation | Status |
|---|---|---|---|---|---|
| Product | Grocery specs (net weight, storage temperature, packaging, grade, origin) | Present for a grocery category | Present from the same schema | Optional | MATCHED |
| Product | Electronics specs (processor, RAM, storage, and the other schema fields) | Present for the matching category | Present from the same schema | Optional. Single values, not a generated matrix | MATCHED |
| Product | Fashion size, colour, fabric, and the other schema fields | Present | Present from the same schema, plus the matrix when variant keys exist | Matrix save is coded and not live-tested | DIFFERENT BEHAVIOUR |
| Product | Restaurant, cafe, and quick-service specs | Present for the matching category | Present from the same schema | Optional | MATCHED |
| Product | Pharmacy kind, dispensing class, generic name, manufacturer, authorization holder, country | Present | Present | Dispensing class required | MATCHED |
| Product | Pharmacy ingredients | Present | Present | Blank names are dropped | MATCHED |
| Product | Pharmacy strength, unit, concentration, dosage form, route | Present for medicines | Present for medicines | Optional | MATCHED |
| Product | Pharmacy pack, units per pack, base unit, selling unit | Present | Present | Units per pack falls back to 1 | MATCHED |
| Product | Pharmacy GTIN, manufacturer reference, registration, storage, temperature | Present | Present | Registration number stays null when blank | MATCHED |
| Product | Pharmacy official price | Present | Present | Minimum, maximum, or both, only for the selected control. Blank stays missing | MATCHED |
| Product | Pharmacy documents | Present | Present | A document without a title is dropped | MATCHED |
| Product | Cost price, wholesale price, a second retail price, discount, margin | Not on the product form. `price_cents` is the retail price | Not added | Not a `ProductCreate` field | NOT APPLICABLE |
| Product | Maximum stock, separate track-inventory checkbox | Not on the product form | Not added | Stock tracking follows item type and the ledger | NOT APPLICABLE |
| Product | Warranty, supplier on the product, product modifiers | Not on the product form. Modifiers live on the menu | Not added | Do not invent them | NOT APPLICABLE |
| Product | Free-text product description | Not on the commercial product form. Pharmacy description stays on the draft and is not edited in the portal form | Same. The hydrated draft is sent back and is not shown | | NOT APPLICABLE |

## Other inventory forms

These POS screens are the existing ones. They have not been rebuilt against Business Pro, and this file does not mark them matched.

| Form | Field | Business Pro | Windows POS | Validation | Status |
|---|---|---|---|---|---|
| Category | Name and the portal's other category fields | Portal category form | POS name prompt and list | Tenant ownership still enforced | MISSING IN POS |
| Brand | Portal brand fields | Portal brand form | POS name prompt and list | | MISSING IN POS |
| Model | Portal model form | `ModelFormModal` | Existing POS model form, not yet compared field by field | | MISSING IN POS |
| Unit | Portal unit fields | Portal unit form | Existing POS unit form | | MISSING IN POS |
| Pricing | Portal price edit | Portal pricing page | Existing POS price drawer | | MISSING IN POS |
| Price list | Portal list fields and product assignment | Portal price lists | POS can create a list. Per-product assignment is not implemented | | MISSING IN POS |
| Price change | Name, apply at, note, new retail | Portal price-change form | Existing POS form, not yet compared field by field | | MISSING IN POS |
| Stock adjustment | Direction, quantity, reason, cost, note | Portal adjustment form | Existing POS drawer | Note length is checked before confirm | MISSING IN POS |
| Purchase order | Multi-line rows | Portal purchase order | One product per order | Accepted for the first Windows gate only | DIFFERENT BEHAVIOUR |
| Transfer | Multi-line rows | Portal transfer | One product per transfer | Accepted for the first Windows gate only | DIFFERENT BEHAVIOUR |
| Stock count | Portal count fields | Portal count form | Existing POS count form | | MISSING IN POS |
| Batch and expiry | Portal batch fields | Portal batch screens | Existing POS screens | Pharmacy lots stay on the pharmacy path | MISSING IN POS |

## Live register check (Stage 1.2.2)

Checked in AxizPOS Inventory Acceptance, grocery profile, Store A, Floor Manager. The drawer was full height of the register window, with a fixed header, a scrolling body, and a fixed Save/Cancel footer. Viewport sizes 1024×768, 1280×800, 1366×768, and 1920×1080 were not each resized.

| Check | Result |
|---|---|
| Create Acceptance Rice 1kg, SKU INV-RICE-01, barcode 6291000002222, category Acceptance Dry Goods, price 3.50, opening quantity 4, reorder 2 | Product created. Catalogue count went from 1 to 2. Opening quantity was an `AUDIT_ADJUSTMENT` of +4, not a raw quantity write |
| Edit price to 3.75 | One row updated to `price_cents` 375. SKU and barcode stayed disabled. No second row |
| Empty submit | Name, price, SKU, barcode, and category-or-model messages stayed on the open form. No success banner |
| Duplicate SKU, then duplicate barcode | Server messages “SKU is already in use.” and “Barcode is already in use.” Values stayed. No extra product |
| Invalid PLU, invalid tax option, invalid brand/model pair | Not clicked in this session |
| Grocery specs | Visible on Produce (Acceptance Inventory Tin), all “Not set”. Hidden for Acceptance Dry Goods, which has no grocery schema |
| Archive rice after it had been sold | Status Archived. `is_active` false. Sale line stayed at 375 cents. On-hand stayed 3. Checkout grid showed only the tin. Cart stayed empty |
| Delete if unused on the sold rice | Not used. The product has a sale and a stock movement |
| Product photo, automatic SKU, automatic barcode, fashion matrix, searchable dropdowns | SKU `ACC-OATS-500G` and barcode `2003884332906` appeared on the rebuilt register. Category search filtered to Acceptance Dry Goods with no Add action for the store-bound manager. Photo upload, saved-gallery edit, and the fashion matrix were not completed before the session locked |

## Remaining parity gaps

1. The rebuilt register opened the new product modal. Create did not finish: the form stayed open after the barcode was filled, and the Windows session locked before a success or error banner could be recorded.
2. Photo compression (`compressImageToWebp`, same limits as Business Pro) and `SavedPhotoGallery` are in this build. Neither was clicked through to a saved product.
3. Category, brand, model, unit, pricing, price list, price change, batch, replenishment, stock count, purchase order, receiving, transfer, and IMEI screens still use the existing register forms.
4. Purchase orders and transfers on the register still send one product per document.
5. Viewports 1024×768, 1280×800, 1366×768, and 1920×1080 were not rechecked. The acceptance window was not resized.
6. The fashion matrix was not run on a fashion tenant.
