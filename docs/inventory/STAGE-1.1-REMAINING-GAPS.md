# Inventory workspace — remaining gaps

Stage 1.2 did not implement these. The Windows register for `com.axizpos.inventory.acceptance` did open Inventory & Stock as Floor Manager on the grocery tenant, submit one stock adjustment from the drawer, and keep the checkout cart mounted. It did not open price-list assignment, a multi-line purchase order, a multi-line transfer, a photo upload, the fashion matrix, or the pharmacy product form. Those stay enhancements.

The order below is the implementation order to use after acceptance, not the order they were first listed.

## Rank

| Priority | Gap | Why it is next | What it depends on |
| --- | --- | --- | --- |
| 1 | Multi-line purchase orders and multi-line transfers | A delivery or a transfer of several products still needs one document per product. | Existing purchase-order, goods-receipt, and transfer services. Stock still increases only on receipt. Pharmacy destination lots stay unreleased. |
| 2 | Price-list product assignment | A price list can be created, but it cannot hold a product price. Selling-price edits are not a price list. | Existing price-list service. Do not rewrite historical sale prices. |
| 3 | Product photo upload | The till shows a placeholder. The Add product drawer opened in Stage 1.2 has name, SKU, barcode, selling price, category, PLU, and sold-by-weight. It has no photo control. | The current image upload and URL fields. Do not store a new blob column unless that is already how images are kept. |
| 4 | Fashion size and colour matrix | Fashion tabs do not expose the generated variant matrix. Size and colour are not a second variant model. | The existing product-model service: create, edit, SKU, stock, barcode, price, and sale lookup. |
| 5 | Remaining pharmacy product fields | The desktop form already asks for the medicine fields the API requires. Extra portal fields need a field-by-field comparison before any are added. | Existing pharmacy schemas only. No new prescription or regulatory claims. |

## 1. Multi-line purchase orders

- Business value: one supplier delivery can be ordered and received as one document.
- Current behaviour: the purchase-order screen creates one product line. Creating or approving the order does not increase stock. Stock increases once, through the existing receiving service.
- Missing workflow: add, remove, and edit several lines on one order, with a line total and an order total. Partial receiving can produce more than one goods receipt.
- Existing API: the current purchase-order and goods-receipt endpoints. They accept one line per operation.
- Backend requirements: line collection on the existing order and receipt models. No second receiving ledger.
- Frontend work: line editor on the existing Purchase orders tab.
- Data migration: none if current single-line rows remain valid one-line orders.
- Dependencies: store scope, supplier, and the receiving service that posts the stock movement.
- Priority: 1, together with multi-line transfers.

## 2. Multi-line transfers

- Business value: moving several products between stores is one transfer, not several.
- Current behaviour: a transfer is one product. Source stock leaves on ship and destination stock arrives on receive. A pharmacy transfer still arrives unreleased.
- Missing workflow: several products on one transfer, with quantity conservation and no duplicate receipt.
- Existing API: the current transfer endpoints, one line per operation.
- Backend requirements: a line collection on the existing transfer. Keep lot allocation and the unreleased pharmacy rule.
- Frontend work: line editor on the existing Transfers tab.
- Data migration: none if current rows remain valid one-line transfers.
- Dependencies: store scope and the existing transfer ledger.
- Priority: 1, together with multi-line purchase orders.

## 3. Price-list product assignment

- Business value: a named price list can price products for a customer, group, or store without changing the catalogue price of past sales.
- Current behaviour: price-list creation can store a name and dates. It cannot store a product price. The Floor Manager register in Stage 1.2 did not show a Price lists tab, which matches the missing `portal:pricing_manage` permission. Selling price is still edited on the product.
- Missing workflow: search a product, set the list price, record effective dates, support bulk assignment, and reject an invalid price.
- Existing API: price-list create exists. Per-product price assignment does not.
- Backend requirements: product-price rows on the existing price-list model, including scope fields the model already has. Historical sale prices stay as recorded.
- Frontend work: product assignment on the price-list screen, shown only to users who already have pricing permission.
- Data migration: none. Existing lists stay lists with no product prices.
- Dependencies: pricing permission and the sale price snapshot.
- Priority: 2. Price-list management is not complete until this exists.

## 4. Product photo upload

- Business value: the till can show the product photo staff already expect in the catalogue.
- Current behaviour: the product image is a placeholder. The Stage 1.2 Add product drawer has no photo field.
- Missing workflow: choose a file, preview it, reject a bad type or an oversized file, upload, replace, and remove only when removal is already safe.
- Existing API: the current image upload and product image URL, where that upload already exists.
- Backend requirements: none beyond the existing upload path.
- Frontend work: file picker and preview on the product drawer.
- Data migration: none.
- Dependencies: the existing image URL field.
- Priority: 3.

## 5. Fashion size and colour matrix

- Business value: fashion staff can create the size and colour combinations they sell without a second product model.
- Current behaviour: size and colour are variant attributes. The generated matrix is not a register screen.
- Missing workflow: generate and edit the matrix, including SKU, barcode, price, and stock where the model service already does that.
- Existing API: the product-model service.
- Backend requirements: none if that service already creates and edits variants. Do not add a second variant table.
- Frontend work: matrix screen on the fashion profile only.
- Data migration: none.
- Dependencies: the existing model service and sale lookup.
- Priority: 4.

## 6. Remaining pharmacy product fields

- Business value: pharmacy staff can complete a medicine record from the register without opening Business Pro for fields the API already accepts.
- Current behaviour: the desktop form asks for the medicine fields the API requires. It is not a full copy of the Business Pro pharmacy form. Stage 1.2 did not open that form.
- Missing workflow: a field-by-field comparison, then any missing field the schema already accepts.
- Existing API: the current pharmacy product schema.
- Backend requirements: none until a comparison shows a field the schema already accepts and the form omits.
- Frontend work: add only those fields. No new prescription or regulatory claims.
- Data migration: none.
- Dependencies: the existing pharmacy schema and lot rules. Generic stock adjustment must not bypass lot controls.
- Priority: 5.

## Separate permission note

Shared categories stay tenant-owned. A store-bound manager receives `403` from the existing store-scope rule. If a branch needs to edit a shared category, that needs a new tenant-scoped permission. It must not be solved by giving the branch manager every tenant catalogue right.
