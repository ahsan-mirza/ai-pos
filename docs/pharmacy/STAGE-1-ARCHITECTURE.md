# Pharmacy vertical — Stage 1 architecture and domain model

Status: design for review. No schema, API, or UI changes are included in this stage.

This document is the Stage 1 deliverable. Implementation starts only after this model is accepted. It is an engineering design, not a legal opinion. A qualified pharmacy compliance professional must validate the regulatory section before any pharmacy tenant is released.

Audit date: 18 November 2026. Source of truth is the current AxizPOS tree: FastAPI tenant models, `packages/shared-types`, `packages/catalog/taxonomy.json`, the Business Pro portal, and the Tauri 2 Windows register.

## 1. What already exists

AxizPOS is one product with a shared catalog, inventory ledger, procurement flow, sales register, and portal. A business profile is a starter preset of capabilities. Code checks capabilities, not profile names (`packages/shared-types/src/capabilities.ts`, mirrored by `apps/api/app/core/capabilities.py` and locked together by `apps/api/tests/test_capabilities.py`).

### Profiles in code today

The product language of four verticals maps to seven stored profiles:

| Product language | Stored `business_profile` | Starter capabilities |
|---|---|---|
| Electronics | `electronics_wholesale` | Serials, warranties, repairs, trade-in, wholesale tiers |
| Wholesale | `wholesale_retail` | Separate profile: tiers, sales orders, credit, cheques |
| Fashion & Retail | `retail_fashion` | Variants, consignment, loyalty, promotions |
| Supermarket & Grocery | `grocery` | Loyalty, promotions, weighed items, FEFO |
| Restaurant & Café | `restaurant`, `cafe`, `quick_service` | Modifiers, open orders, KDS, recipes; tables and delivery vary |

There is no `pharmacy` profile, no pharmacy subtype, and no pharmacy branch in `packages/catalog/taxonomy.json`. Signup subtypes live in `packages/shared-types/src/signup.ts`. Grocery subtypes (`grocery_shop`, `grocery_supermarket`, and the rest) only toggle grocery capabilities. Reusing one of those and renaming the label would turn pharmacy into a grocery preset. That is rejected.

### Tenant isolation

Operational rows use `TenantScoped` (`apps/api/app/models/base.py`): every pharmacy table must carry `tenant_id` and tenant-unique keys. The control-plane database (`alembic_control`) holds tenants, billing, and demo identity. `tenants.demo_business_type` is constrained to the current demo codes. A pharmacy demo tenant is out of scope until Stage 10, and that constraint must be migrated then, not implied by application code.

### Catalog

`products` is the sellable SKU. Money is integer cents. `tax_category` is per product (`STANDARD` and the existing zero/exempt treatments). Sale lines snapshot `tax_rate_bps`. Nothing in the model assumes one VAT rate for a vertical.

Identity already on the product: SKU, barcode (tenant-unique), name, brand string and `brand_id`, `model_number`, category and subcategory foreign keys, variant attributes and signature, `specifications` JSON, prices, cost, currency, active flag, `minimum_age`, sellable units, images (`product_images`).

There is no long description, no GTIN column, no generic name, and no regulatory classification. Search is a persisted `search_text` generated column over name, model, barcode, SKU, category, brand, season, and collection. Generic-name search needs an explicit extension of that generated column.

Categories are exactly two levels: `categories` and `sub_categories`, both tenant-scoped, with name, code, and description. There is no image, display order, active flag, product-type binding, or required-attribute binding. Deeper trees are not supported. Pharmacy should stay at Category → Subcategory → Product and extend the two existing tables. A third level would be a new hierarchy, not a reuse.

Starter trees are inserted by `ensure_taxonomy` from `packages/catalog/taxonomy.json` at provisioning. Existing names are left alone. A pharmacy key in that file is the right seeding mechanism. The client specification picker in `packages/shared-types/src/specifications.ts` is a different mechanism: it matches category-name keywords (`matchGrocery` returns one `GROCERY_ITEM` schema). Pharmacy forms must not be added there. A keyword match would show the same fields for every medicine and would freeze the taxonomy in the client.

Attributes (`product_attribute_definitions` / `product_attribute_values`, migration `20261111_0104`) are tenant definitions with a data type, options, a `profiles` list, and a copy onto `products.specifications`. They are the right place for non-gating display fields (device model, flavor, warranty months). They are the wrong place for a dispensing rule. A JSON specification cannot be the thing that stops a cashier selling a prescription medicine.

Variants already exist: `product_models` plus `products.variant_signature`, unique per model and combination. Strength and pack size must be separate SKUs under one model. Different active ingredients must not share a signature.

Units of measure (`units_of_measure`) are whole-number factors of a base piece (`PIECE`, `BOX_10`, `CARTON_100`, plus tenant codes). Stock and sale quantities stay in base units. That supports “carton of 200 tablets” as `CARTON_200` with factor 200, and a strip as `STRIP_10` with factor 10. It does not store a pack graph (carton contains boxes contains strips). Intermediate packs are sibling factors of the same base. Fractional dispensing is already impossible for piece stock because quantities are integers. Community-pharmacy v1 sells whole base units. Splitting a bottle into millilitres is compounding and is not part of `community_pharmacy`.

### Inventory and the thing currently called a batch

`inventory_levels` is one on-hand and reserved quantity per product per store. `stock_movements` is the append-only ledger. Only `services.inventory` writes quantities.

`purchase_batches` / `batch_items` / `batch_allocations` are cost layers, not manufacturer lots (`apps/api/app/models/batch.py`):

- `PurchaseBatch.batch_number` is the receipt document number, unique per tenant, not the manufacturer lot.
- One purchase batch holds many products.
- `BatchItem` has quantity imported, quantity remaining, unit cost, selling price, and an optional `expiry_date`.
- There is no manufacturer lot, manufacturing date, quarantine, damage hold, recall flag, or storage location.
- `batch_allocations` record which layer a stock movement drew, and `sale_items.batch_item_id` points at the first layer. The full split stays on allocations.
- Manual adjustments can pass a `lot_number`, but `record_adjustment_layer` writes it into `batch_number` (32 characters, tenant-unique). Two products cannot share a manufacturer lot code stored that way.

FEFO (`apps/api/app/services/batch_ledger.py`) is capability-gated. With `fefo` on, open lines sort by soonest expiry, then undated, then expired. Expired lines are still drawn when nothing fresher remains. The allocation is flagged `expired=true` and an `EXPIRED_STOCK_SOLD` audit row is written. The module comment says an offline register may already have sold them. Grocery must keep this behavior. Pharmacy must not call it.

Goods receipt (`receive_purchase_order`) books stock immediately and opens one cost layer per purchase-order line. `ReceiveLineIn` has quantity, serials, and a shelf location. It has no lot and no expiry. Each purchase-order line may appear once per receipt. A second manufacturer lot on the same line cannot be received without a second receipt, and even then the layer has no lot number. `record_receipt_layer` does not set `expiry_date`.

Expiry alerts (`FefoSettings.alert_days`, default 14, range 1–365) and write-off of already-expired lines exist. Thresholds are a single window, not 180/90/60/30/7. Write-off uses `DAMAGE_SHRINKAGE` / `DAMAGED_OR_EXPIRED`. There is no quarantine, release, or recall.

### Procurement, customers, sales, returns

Purchase orders, GRN, suppliers, supplier bills (one bill can point at one GRN and one purchase batch), supplier payments, and allocations already exist. Suppliers have contact, lead time, MOQ, pack size, payment terms, and TRN. They have no licence, licence authority, or pharmaceutical-supplier classification.

Customers are retail or wholesale accounts: contact, birthday, gender, notes, tags, consent flags split between receipts and marketing, loyalty points, credit ledger. Clinical data must not be stored in `notes`, `tags`, or `risk_detail`.

Sales, tenders, tax snapshots, promotions, manual discounts, margin-floor approvals, and price lists are shared. `ApprovalRequest` covers `PRICE_OVERRIDE`, `BELOW_FLOOR`, `CREDIT_LIMIT`, and `REFUND`. It is a manager PIN, not a pharmacist verification. A cashier with `pos:discount` must not be able to approve dispensing.

Returns restock when the condition policy says `restock` (`returns_service`). That puts the unit back on the original batch. Pharmacy returns of medicines must default to not restocking. The return framework itself is reused.

### POS, portal, assistant

The Windows register is `apps/desktop` (Tauri 2). Local SQLite (`src-tauri/src/db.rs`) caches products with an aggregate `stock_quantity`, not batches. `sync_queue` deduplicates on `idempotency_key`. Cached users carry permissions and a PIN hash. Terminal activation already exists.

Business Pro is `apps/web`. Navigation is capability- and permission-gated in `apps/web/src/components/layout/navigation.ts`. New pharmacy screens belong in that shell.

The assistant (`assistant_tools.py`) runs tenant-scoped tools the principal is allowed to call: sales, stock value, slow stock, shrink, payables, and others. `price_suggestions` can propose expiry markdowns. There is no clinical tool. New pharmacy tools must be operational and must not read patient clinical columns.

There is no workflow engine, no prescription, no pharmacist licence, no insurance claim, no temperature log, and no recall record.

## 2. Design locks

These are constraints on every later stage.

1. Medicine master is not a batch. One SKU has many manufacturer lots, expiries, and purchase costs. Lot fields never go on `products`.
2. Brand is not the generic. `products.brand` stays the trade name. The scientific name lives on the pharmacy extension and in search. Substitution is a pharmacist action, never an automatic sale of a different SKU.
3. A prescription is not a sales invoice and not a `SalesOrder`. It has its own validity, verification, dispensing, and audit life. The invoice is created only when a dispensing record is posted through the existing sale pipeline.
4. FEFO records the batch actually consumed. Pharmacy allocation excludes expired, quarantined, recalled, and unreleased lines. It fails the sale when eligible quantity is short. Grocery FEFO is unchanged, including its current expired-last fallback.
5. Clinical information is not customer data. Allergies, prescription history, and dispensing history live on patient tables with their own permissions. Loyalty, phone, and marketing consent stay on `customers`.
6. Offline POS does not dispense restricted products. OTC may follow an explicit offline policy. Prescription and controlled lines are blocked when the server cannot verify the current authorization. A cached stock figure never overrides a server recall or quarantine watermark.

Additional rules:

- Do not add a second POS or a second ERP.
- Do not duplicate `inventory_levels` with a parallel quantity that can drift.
- Do not infer OTC from the product name or the category name.
- Do not invent registration numbers, official prices, interaction data, or insurance approvals.
- Do not mark a recall as reported to a regulator unless an integration returns that status.
- Do not let a promotion, a manager discount, or `pos:price_override` bypass a dispensing or price-control rule.
- Job title and role name do not prove a pharmacist licence.
- Only `community_pharmacy` is implemented. `chain_pharmacy`, `hospital_pharmacy`, `online_pharmacy`, and `compounding_pharmacy` stay off the signup list until their licensing workflow exists. Clinical-pharmacist duties in Federal Law No. 8 of 2019 (treatment plans, laboratory requests, administration) are out of scope for a community pharmacy.

## 3. Profile and capabilities

New profile, same conventions as the existing presets:

| Field | Value |
|---|---|
| `business_profile` | `pharmacy` |
| Group | `retail_trade` |
| Label | Medical Pharmacy |
| Short label | Pharmacy |
| Settings label | Pharmacy settings |
| Subtype in v1 | `community_pharmacy` only |

Starter capabilities, independent of grocery:

- `fefo` — required, but the pharmacy policy below replaces the grocery expired-last draw
- `loyalty`
- `promotions` — engine reused, with a pharmacy price-control hook
- `card_terminals`

New capabilities, eligible for `pharmacy` and not added to grocery’s eligible list:

| Capability | What it switches on |
|---|---|
| `pharmacy_catalog` | Medicine master, ingredients, product kind, dispensing class, pharmacy forms |
| `prescriptions` | Prescription lifecycle and pharmacist verification |
| `controlled_medicines` | Restricted register, custody, reconciliation. Off until the tenant licence allows it |
| `pharmacy_patients` | Clinical patient profile separated from the customer |
| `pharmacy_insurance` | Manual claim tracking. No payer until one is configured |
| `cold_chain` | Locations, readings, excursion quarantine |
| `product_recall` | Recall holds and batch trace |

`weighed_items` stays off the pharmacy preset. A community pharmacy does not sell produce by the kilo. Optional later add-ons that already exist and are commercially sensible: `b2b_credit` for clinic accounts, `sales_orders` for ward or clinic supply, `gift_cards`, `multi_currency`, `deep_analytics`, `ai_insights`, `sales_insights`, `axiz_reach`, `uae_einvoicing`. Those are eligible add-ons, not the starter set. `serial_tracking` stays an electronics capability. A GTIN is not an IMEI.

Pharmacy FEFO policy (stored on `module_settings`, validated like `FefoSettings`):

- `mode`: `strict` for pharmacy, absent for grocery
- `alert_thresholds_days`: default `[180, 90, 60, 30, 7]`, each between 1 and 365, tenant-editable
- `block_expired_sales`: true when strict
- `require_release_before_sale`: true when strict
- Grocery continues to read only `alert_days`

`module_settings` is one JSON document on `business_settings`. Extra pharmacy sections follow the existing `_Section` pattern with `extra="forbid"`.

## 4. Category taxonomy

Seed through `taxonomy.json` under `"pharmacy"`. Tenants can rename, reorder, deactivate, and add categories in Business Pro. The seed is a template, not a permanent enum.

Category extensions (nullable, defaults preserve current tenants):

- `display_order` integer, default 0
- `is_active` boolean, default true
- `image_key` nullable, same media-key pattern as product images
- `product_kinds` JSON list, empty means unrestricted
- `form_policy` string, optional hint (`medicine`, `device`, `supplement`, `cosmetic`, `general`)

Subcategories get `display_order` and `is_active`.

Veterinary is seeded inactive. It becomes active only when the tenant licence flag `veterinary_permitted` is set by an authorized user. The seed does not turn it on.

### A. Prescription Medicines (`RX`)

Antibiotics. Cardiovascular medicines. Diabetes medicines. Respiratory medicines. Gastrointestinal medicines. Dermatology medicines. Neurological medicines. Pain management. Hormonal medicines. Ophthalmic medicines. ENT medicines. Urological medicines. Women's health. Men's health. Other prescription medicines.

`product_kinds`: `MEDICINE`. `form_policy`: `medicine`. The category does not set the dispensing class. A pain-management SKU can be OTC, prescription, or controlled. The class is a field on the product, confirmed against the tenant’s regulatory policy.

### B. Over-the-Counter Medicines (`OTC`)

Pain relief. Fever relief. Cold and flu. Cough and throat. Allergy relief. Digestive health. Antacids. Oral rehydration. First aid. Topical treatments.

`product_kinds`: `MEDICINE`. Same rule: the subcategory name is not proof of OTC status.

### C. Vitamins and Supplements (`VIT`)

Multivitamins. Vitamin C. Vitamin D. Vitamin B complex. Calcium. Iron. Magnesium. Zinc. Omega-3. Probiotics. Sports nutrition. Other supplements.

`product_kinds`: `SUPPLEMENT`. `form_policy`: `supplement`.

### D. Medical Devices (`DEV`)

Blood glucose meters. Glucose test strips. Blood pressure monitors. Thermometers. Nebulizers. Pulse oximeters. Mobility aids. Medical monitoring devices.

`product_kinds`: `DEVICE`. `form_policy`: `device`.

### E. Medical Supplies (`SUP`)

Bandages. Dressings. Gauze. Syringes. Needles. Gloves. Masks. Medical tapes. Wound care. Disposable supplies.

`product_kinds`: `SUPPLY`. `form_policy`: `general`.

### F. Mother and Baby Care (`BABY`)

Infant formula. Baby food. Baby skincare. Baby hygiene. Diapers. Maternity care. Breastfeeding accessories.

`product_kinds`: `NUTRITION`, `PERSONAL_CARE`, `ACCESSORY`. `form_policy`: `general`, with nutrition fields when kind is `NUTRITION`.

### G. Personal Care (`CARE`)

Skin care. Hair care. Oral hygiene. Dental products. Feminine hygiene. Men's grooming. Personal hygiene.

`product_kinds`: `PERSONAL_CARE`. `form_policy`: `general`.

### H. Cosmetics and Beauty (`COS`)

Sunscreen. Moisturizers. Dermatological skincare. Beauty products. Fragrances. Cosmetic accessories.

`product_kinds`: `COSMETIC`. `form_policy`: `cosmetic`.

### I. Nutrition and Wellness (`NUT`)

Medical nutrition. Dietary products. Special nutrition. Health foods.

`product_kinds`: `NUTRITION`. `form_policy`: `supplement`.

### J. Veterinary Products (`VET`, inactive until licensed)

Veterinary medicines. Animal supplements. Veterinary supplies.

`product_kinds`: `VETERINARY`. Hidden from POS and purchasing while the category is inactive.

### K. Pharmacy Accessories (`ACC`)

Pill organizers. Medicine dispensers. First-aid kits. Hot/cold packs. Mobility accessories. Other pharmacy accessories.

`product_kinds`: `ACCESSORY`. `form_policy`: `general`.

## 5. Product model

### 5.1 What stays on `products`

SKU, barcode, name (trade / display name), brand, category, subcategory, model and variant signature, images, retail price, default cost, last purchase cost, currency, tax category, price-includes-tax, active flag, sellable units, minimum age, price tiers (`product_prices`). Wholesale price uses the existing tier prices. A second wholesale column on the pharmacy row would fork pricing.

Internal code is the existing SKU. A second internal code is not added.

### 5.2 `pharmacy_product_details` (new, 1:1, tenant-scoped)

Present only for pharmacy-catalog products. Other profiles never read it.

| Group | Columns |
|---|---|
| Identity | `product_id` primary key and foreign key, `product_kind`, `generic_name`, `manufacturer`, `marketing_authorization_holder`, `country_of_origin`, `description`, `gtin`, `manufacturer_product_ref` |
| Medicine | `dosage_form`, `route`, `strength_amount`, `strength_unit`, `strength_display`, `concentration`, `pack_size_label`, `units_per_pack` |
| Packs | `base_unit_code`, `purchase_unit_code`, `selling_unit_code`, `dispense_unit_code`, `fractional_dispensing_allowed` (default false) |
| Regulation | `dispensing_class`, `classification_source`, `pharmaceutical_class`, `registration_number`, `registration_authority`, `marketing_authorization_ref` |
| Storage | `storage_condition`, `temp_min_c`, `temp_max_c`, `cold_chain`, `handling_instructions`, `warnings_text`, `leaflet_document_id` |
| Commercial controls | `price_control` (`NONE`, `MINIMUM`, `MAXIMUM`, `FIXED`), `min_price_cents`, `max_price_cents`, `discount_eligible`, `promotion_eligible`, `offline_policy` (`ALLOW` or `BLOCK`) |
| Substitution | `substitution_group_id` nullable. Same generic, strength, form, and route may share a group. The register lists alternatives. It never swaps them. |

`dispensing_class` is one of `OTC`, `PRESCRIPTION`, `CONTROLLED`, `SEMI_CONTROLLED`, `RESTRICTED`, `SPECIAL_HANDLING`.

`classification_source` is `TENANT_DECLARED` until an authorized integration sets `AUTHORITY_CONFIRMED`. The POS treats both as restrictive: the class still blocks free sale. The source only records whether the class was confirmed by an authority feed. Staff cannot type a class and have the system call it government-verified.

`registration_number` is nullable. The application never generates one.

`price_control = FIXED` blocks discounts and promotions. If the tenant policy says an official price is required and `max_price_cents` is null, the SKU cannot be sold. The system does not look up or invent a Ministry price.

`offline_policy` defaults to `BLOCK` for every class except `OTC`, and the OTC default is `ALLOW` only when the tenant turns offline OTC on. A user cannot set `ALLOW` on prescription, controlled, semi-controlled, restricted, or special-handling lines. The server rejects that write.

### 5.3 `product_ingredients` (new)

One row per ingredient: position, name, `strength_amount`, `strength_unit`, `is_active`. A medicine requires at least one active ingredient. A device does not. Supplements use the same table for labelled ingredients. This is structured data, not a comma-separated specification.

### 5.4 `product_documents` (new)

Leaflet, registration, supplier file, or other. Storage keys follow `product_images` (tenant media folder). Access is permission-checked. Images stay on `product_images`. A leaflet is not a gallery photo.

### 5.5 Attribute matrix

Gating columns are enforced by the server. Display attributes are `ProductAttributeDefinition` rows with `profiles: ["pharmacy"]`, copied to `specifications` for the register cache. Category `form_policy` chooses which display group to show. Irrelevant groups are omitted.

| Product kind | Required gated fields | Display attributes | Hidden |
|---|---|---|---|
| `MEDICINE` | Generic name, at least one active ingredient, strength, strength unit, dosage form, route, pack size, units per pack, dispensing class, base unit | Manufacturer, MAH, country, warnings (entered from a leaflet), registration reference | Device model, scent, shade |
| `DEVICE` | Manufacturer, dispensing class (usually OTC or `SPECIAL_HANDLING`), base unit | Model, compatibility, warranty months, power source | Strength, route, active ingredient |
| `SUPPLY` | Base unit, dispensing class | Sterile flag, material, size label | Strength, prescriber fields |
| `SUPPLEMENT` | Pack size, base unit, dispensing class | Ingredients via `product_ingredients`, serving size, nutritional notes | Prescription workflow unless class is not OTC |
| `COSMETIC` | Brand, volume or pack, base unit, dispensing class | Shade, scent, skin type, volume | Dosage form, route, pharmacist approval |
| `PERSONAL_CARE` | Brand, pack, base unit, dispensing class | Volume, variant scent or size | Clinical fields |
| `NUTRITION` | Pack, base unit, dispensing class | Age stage, dietary label, ingredients | Controlled-drug register |
| `VETERINARY` | Same as medicine, plus species label. Category must be active | Target species, withdrawal note if the tenant enters one | Shown only when the licence flag is on |
| `ACCESSORY` | Base unit, dispensing class | Size, material | Medicine fields |

Dosage-form options are tenant-configurable with this seed: tablet, capsule, syrup, suspension, oral drops, cream, ointment, gel, injection, eye drops, ear drops, nasal spray, inhaler, suppository, powder, sachet, patch, solution. The list is data, not a check constraint that would need a migration for every new form.

Strength units seed: mg, g, mcg, IU, %, mg/ml, mcg/dose. Pack units reuse UOM codes: carton, box, pack, bottle, strip, blister, tablet, capsule, tube, sachet, vial, ampoule, piece.

Variant axes that may split a model into SKUs: strength, pack size, flavor, concentration, packaging. Active ingredient set is not a variant axis. Changing the ingredient creates a different model.

### 5.6 Search

Extend the generated `search_text` to include `generic_name` and GTIN, with the same separator-stripping used for barcode. This is a migration that rebuilds the generated column. POS lookup continues to use barcode, SKU, and name, and adds generic name when the pharmacy catalog capability is on.

## 6. Batch and inventory

Do not create a second quantity store. Extend `batch_items`.

New nullable columns, defaults chosen so grocery rows stay sellable:

| Column | Grocery default | Pharmacy use |
|---|---|---|
| `manufacturer_lot` | null | Required before release |
| `manufacturing_date` | null | Optional |
| `goods_receipt_line_id` | null | Line that received this lot |
| `lot_status` | `AVAILABLE` | `PENDING_RELEASE`, `AVAILABLE`, `QUARANTINED`, `DAMAGED`, `RECALLED`, `SUPPLIER_RETURN`, `WRITTEN_OFF` |
| `storage_location_id` | null | Shelf, refrigerator, or safe |
| `quantity_reserved` | 0 | Held for an approved prescription |

`quantity_remaining` stays the physical quantity still in this layer. Sellable quantity is `quantity_remaining - quantity_reserved` only when `lot_status` is `AVAILABLE` and the expiry date is today or later. Expired, pending, quarantined, damaged, recalled, returned, and written-off layers contribute zero sellable quantity.

A partial quarantine splits the layer: the original line’s `quantity_remaining` drops by a stock movement of type `QUARANTINE_HOLD` (new movement type), and a sibling `batch_items` row carries the held quantity at the same cost and lot number with `lot_status = QUARANTINED`. Release is the reverse movement. Grocery never emits these movement types.

`batch_movements` (new) records the status change, actor, reason, and related document. `stock_movements` remains the quantity ledger. Both are required for an adjustment.

Pharmacy FEFO draw, inside `batch_ledger.open_items`, only when the product has pharmacy details and the tenant policy is strict:

1. Lock open layers for the product and store.
2. Drop pending, quarantined, damaged, recalled, supplier-return, and written-off lines.
3. Drop expired lines. Do not append them at the end.
4. Sort by expiry ascending, then received time (stable FIFO tie-break).
5. Allocate base-unit quantity. Write `batch_allocations` as today.
6. If the eligible quantity is short, fail the sale. Do not fall through to unbatched on-hand.

Grocery `open_items` keeps today’s sort, including the expired-last fallback. The branch is on the product and the tenant policy, not on a copied function that can drift.

Unbatched pharmacy stock (on-hand with no eligible layer) cannot be sold. Grocery may still sell unbatched stock after layers are empty, which is the current rule and must stay.

### Receiving

`ReceiveLineIn` gains an optional `lots` array: manufacturer lot, manufacturing date, expiry date, quantity, storage location. The quantities must sum to the line quantity. One purchase-order line still appears once per receipt. The array is how one line becomes several layers.

For a pharmacy product:

- Lot number and expiry are required.
- The layer is created as `PENDING_RELEASE`.
- On-hand increases, sellable does not.
- An authorized user releases the line after checking lot and expiry. That is the moment it can be sold.
- Partial deliveries stay as they are: `partially_received` until ordered quantity is met.
- Supplier invoice matching stays on `supplier_bills`, which already link the GRN and the purchase batch. A receipt with several lots still has one GRN. Each lot layer points at the same `goods_receipt_id` and its own line.

Non-pharmacy receipts omit `lots`. `record_receipt_layer` behavior is unchanged.

### Trace

A lot is traced by `batch_items.id` through `goods_receipt_id`, `purchase_order_id`, `batch_allocations`, `sale_items`, transfers (`TRANSFER_OUT` / `TRANSFER_IN` already move layers via `on_movement`), and dispensing records. Reports follow those foreign keys. They do not scan free-text notes.

## 7. Prescription and dispensing

New tables, all tenant-scoped.

### `prescriptions`

Reference, patient id, customer id (the retail identity, nullable until linked), prescriber name, prescriber licence number, facility, issued on, valid until, source (`MANUAL`, `IMAGE`, `ELECTRONIC_REF`), authentication (`MANUAL_UNVERIFIED` or `AUTHORITY_CONFIRMED`), external reference, document id, status, pharmacist id, rejection reason.

Status: `RECEIVED` → `VALIDATED` → `IN_REVIEW` → `APPROVED` or `REJECTED` → `PARTIALLY_DISPENSED` or `DISPENSED` → `CLOSED` or `EXPIRED`.

A manual or photographed prescription remains `MANUAL_UNVERIFIED` forever unless an electronic-prescription adapter returns a confirmation. The UI says “entered by staff”, not “electronically authenticated”.

Validation before approval:

- Patient identity required by the tenant policy (community default: name plus a contact or an identity reference the tenant marks required).
- Prescriber name and licence number required.
- Issued date and validity date required. Past validity cannot be approved.
- Each line has product, strength, dosage, route, frequency, duration, quantity, and refills allowed.
- Product dispensing class is prescription, controlled, semi-controlled, or restricted. An OTC line does not need a prescription. A controlled line also needs the controlled-policy checks.
- The product’s strength and form must match the prescribed line. A mismatch is a rejection or a recorded substitution, not a silent swap.

### `prescription_items`

Product id, prescribed quantity in base units, quantity dispensed, quantity remaining, refills authorized, refills used, dosage text, route, frequency, duration, substitution flag and the substituting product id if a pharmacist recorded one.

### `pharmacist_credentials`

User id, licence number, issuing authority (free text plus a code the tenant configures: `MOHAP`, `DHA`, `DOH`, or another), valid from, valid until, status (`ACTIVE`, `EXPIRED`, `REVOKED`). Unique per tenant, user, and authority. Role assignment does not create this row.

### `pharmacist_duty`

User id, store id, started at, ended at. Dispensing of a non-OTC line requires an open duty row for that store and a credential that is `ACTIVE` on the dispensing date. The tenant policy can require the pharmacist-in-charge credential for controlled lines.

### `pharmacist_verifications`

Prescription id, pharmacist user id, credential id, decision (`APPROVED` or `REJECTED`), note, created at. Append-only.

### `dispensing_records`

Prescription item id, sale id, sale item id, batch item id, quantity, pharmacist user id, verification id, dispensed at. Created in the same transaction as the sale and the batch allocation.

Checkout rules:

- OTC: existing sale path, plus strict FEFO allocation when the product is a pharmacy product.
- Prescription class: a sale line is rejected unless it references an approved prescription item with remaining quantity, an active verification, and an on-duty pharmacist. The line quantity cannot exceed remaining quantity.
- Controlled and semi-controlled: the controlled policy must also pass (section 8). `pos:discount`, `pos:price_override`, and `ApprovalRequest` of kind `PRICE_OVERRIDE` do not satisfy this.
- Partial dispensing reduces `quantity_remaining` and sets `PARTIALLY_DISPENSED`.
- A repeat is allowed only when refills remain and the prescription is still valid.

Audit: verification, dispensing, rejection, and quantity change write `audit_logs` with new action types. They are not stuffed into `MANAGER_OVERRIDE`.

## 8. Controlled medicines

No schedule table is shipped. Federal Law No. 14 of 1995 is referenced by Federal Law No. 8 of 2019 Article 50. Encoding one emirate’s list, or a guessed federal list, would be a false compliance claim.

`regulatory_policies` (tenant-scoped, one active row):

- Jurisdiction label and code (`FEDERAL`, `DUBAI`, `ABU_DHABI`, `SHARJAH`, `AJMAN`, `UAQ`, `RAK`, `FUJAIRAH`, or a future code). The code selects which requirement set the tenant has entered. It does not download a law.
- Pharmacy licence number, authority, expiry. Empty licence blocks non-OTC dispensing.
- `controlled_dispensing_enabled` boolean, default false.
- `veterinary_permitted` boolean, default false.
- Requirement matrix the tenant, or a later adapter, fills: for each dispensing class, whether a prescription is required, whether a special form number is required, maximum validity days, whether a witness is required, whether a running register is required, whether offline is forbidden.

`controlled_ledger_entries` (only when the capability is on and the flag is true): product, batch item, direction (`IN`, `DISPENSE`, `ADJUST`, `RETURN`, `DISPOSAL`, `HANDOVER`), quantity, balance after, prescription id, pharmacist id, witness id, reason, document id. This is a register beside the stock ledger, not a replacement.

Custody handover is a pair of entries (out from one pharmacist, in to another) with both credentials checked.

Adjustments require a reason and `controlled:adjust`. Discrepancies are a status on a stock-count variance that references the register balance, investigated by a user with `controlled:investigate`. Disposal requires `controlled:dispose` plus a document. Nothing in this module reports itself to MOHAP, DHA, DOH, or EDE.

If `controlled_dispensing_enabled` is false, products in `CONTROLLED` or `SEMI_CONTROLLED` cannot be received into `AVAILABLE` and cannot be sold. They can be recorded as catalog items so the pharmacy can see them, and receiving leaves them `PENDING_RELEASE` with no release action.

## 9. Patients, insurance, cold chain, recall, returns

### Patients

`pharmacy_patients` links to `customers.id`. Clinical columns: date of birth (duplicated here even if the customer has a birthday, so a retail edit does not become a clinical edit), sex as recorded for dispensing, allergies (text plus structured rows in `patient_allergies`), identity reference, consent for storing clinical data, privacy flags.

`customers:manage` can edit the customer. It cannot read allergies, prescriptions, or dispensing history. Those need `patients:read` or `patients:write`. List exports of customers omit clinical columns. Assistant tools do not join `pharmacy_patients`.

Prescription history and dispensing history are queries over the prescription and dispensing tables, not copies on the customer.

### Insurance

`insurance_payers`, `insurance_policies` (patient, member id, policy number), `insurance_claims` (prescription or sale, amounts, co-pay, deductible, status, rejection reason, resubmission link).

Statuses: `MANUAL_PENDING`, `SUBMITTED`, `REJECTED`, `RESUBMITTED`, `SETTLED`. Creating a claim sets `MANUAL_PENDING`. No code path sets `SETTLED` without a user entering a settlement reference or a payer adapter returning one. There is no simulated approval.

The sale takes the patient co-pay through the existing tender flow. The claim balance is not a fake payment.

### Cold chain

`storage_locations`: store, name, kind (`AMBIENT`, `REFRIGERATOR`, `FREEZER`, `SAFE`), target min and max. `temperature_readings`: location, taken at, celsius, source (`MANUAL` or `DEVICE`), device reference. A device source is accepted only from an adapter that is actually configured. The manual form is the only built-in writer.

An excursion (reading outside the location range, or outside the product’s range for stock stored there) sets every `AVAILABLE` cold-chain layer in that location to `QUARANTINED` and writes batch movements. Nothing automatically releases them. Release uses the same authorized release action as receiving, with an excursion-review note.

### Recall

`recalls`: reference, source text, severity, reason, status (`OPEN`, `CONTAINED`, `CLOSED`), opened by. `recall_items`: product id, manufacturer lot (and optional batch item ids once matched). Matching sets those layers to `RECALLED`, which FEFO already excludes. Affected sales are `batch_allocations` joined to sale items for those layers. Status `CLOSED` means the tenant finished its internal workflow. A separate `regulator_report_status` stays `NOT_REPORTED` unless an adapter sets `REPORTED`.

### Returns

Customer return of a pharmacy product: the existing return document, original sale, and batch allocation identify the lot. Condition `RESELLABLE` is rejected for dispensing classes other than OTC, and even OTC defaults to quarantine unless the user has `inventory:release_batch` and explicitly releases. Refunds use the existing tender reversal. Supplier returns use the existing purchasing documents plus the layer status `SUPPLIER_RETURN` and a credit against the supplier bill. Expired and damaged stock use quarantine, then write-off, with a document and `inventory:write_off`. Write-off does not delete the layer. It sets status and zeroes remaining through the ledger.

## 10. Permissions

Roles remain tenant-defined bundles of permissions. Seeding suggested roles is a convenience at pharmacy provisioning. Licensing is the credential table, not the role name.

New permissions, same `domain:action` style:

| Permission | Holds |
|---|---|
| `pharmacy:configure` | Profile settings, regulatory policy, category activation including veterinary |
| `pharmacy:catalogue` | Medicine master and documents |
| `prescriptions:read` | Read prescriptions and dispensing history |
| `prescriptions:write` | Capture and edit a prescription before approval |
| `prescriptions:verify` | Approve or reject. Also requires an active credential |
| `prescriptions:dispense` | Post a dispensing sale. Also requires duty and credential |
| `controlled:read` | Read the controlled register |
| `controlled:dispense` | Dispense when policy allows. Subset of verify plus the controlled flag |
| `controlled:handover` | Custody handover |
| `controlled:adjust` | Register adjustment |
| `controlled:dispose` | Disposal |
| `controlled:investigate` | Discrepancy workflow |
| `patients:read` | Clinical patient fields |
| `patients:write` | Edit clinical fields and consent |
| `insurance:manage` | Payers, policies, manual claims |
| `cold_chain:read` | Locations and readings |
| `cold_chain:write` | Readings and excursion review |
| `recall:manage` | Open a recall and match lots |
| `inventory:release_batch` | Release pending or quarantined layers |
| `inventory:quarantine` | Quarantine and mark damaged |
| `reports:pharmacy` | Pharmacy reports that include dispensing or controlled data |
| `reports:pharmacy_clinical` | Reports that include patient identity. Separate from ordinary sales reports |

Suggested bundles:

| Role | Permissions | Explicitly without |
|---|---|---|
| Pharmacist-in-charge | configure, catalogue, verify, dispense, controlled read/dispense/handover/investigate, patients, recall, release, pharmacy reports | Payroll, and controlled adjust/dispose unless granted |
| Licensed pharmacist | verify, dispense, patients read/write, prescriptions read/write, pharmacy reports | configure, controlled dispose, role management |
| Pharmacy technician | catalogue read via portal inventory, quarantine, receiving support, prescriptions write | verify, dispense of non-OTC, controlled dispense, patients clinical export |
| Cashier | `pos:access`, OTC sale, payments | verify, dispense, `pos:discount` on price-controlled lines, patients clinical |
| Inventory manager | purchasing, GRN, release, quarantine, supplier returns, write-off | verify, controlled dispense |
| Pharmacy manager | reports, staff within `users:update`, pricing, inventory oversight | verify, unless they also hold a credential and `prescriptions:verify` |
| Auditor | read-only: audit, pharmacy reports, controlled read, prescriptions read | Every write permission |

A user with the cashier bundle and a manager discount permission still cannot verify a prescription. The sale service checks the dispensing permission and the credential, not “any manager permission”.

## 11. UAE regulatory capability matrix

Sources used for the product boundaries, not encoded as a rule engine:

- Federal Law No. 8 of 2019 on Medical Products, the Pharmacy Profession and Pharmaceutical Establishments, published on the UAE legislation portal. Articles 31 and 32 separate products that require a prescription from those that do not, and Article 32 leaves the non-prescription list to a ministerial resolution. Article 48 prohibits selling unfit, expired, unauthorized, counterfeit, or smuggled products, and selling at a price other than the one set by the Ministry. Article 49 lists what a prescription must bear and prohibits dispensing a prescription-only product without one. Article 50 adds narcotic and psychotropic requirements under Federal Law No. 14 of 1995, including a designated form and a maximum age of the prescription. Article 4 and the recall provisions require the establishment to follow recall procedures.
- MOHAP’s notice on services transferred to the Emirates Drug Establishment: community-pharmacy and compounding-pharmacy licensing stay with MOHAP. Factories, warehouses, medical stores, and marketing offices move to EDE. EDE also publishes medicine price lists and controlled-custody registration. Those are external services.
- Tatmeen is the national track-and-trace platform announced by MOHAP with the Department of Health — Abu Dhabi and the Dubai Health Authority. It is not connected.

The matrix is what AxizPOS will claim. “Local” means the tenant types it and the application enforces the tenant’s own policy. “Not built” means the product must not show the integration as live.

| Capability | v1 behavior | Authority feed |
|---|---|---|
| Community pharmacy licence record | Local fields, required for non-OTC | Not built. MOHAP licence lookup is not called |
| Pharmacist licence record | Local credential, expiry blocks dispensing | Not built. No MOHAP, DHA, or DOH register query |
| Product registration number | Stored if staff enter it. Never generated. Source stays `TENANT_DECLARED` | Not built. No EDE or MOHAP registration API |
| Official price | `price_control` if staff enter a ceiling or fixed price. Empty price blocks sale when policy requires it | Not built. No price-list download |
| OTC versus prescription | Staff-set class, enforced regardless of category name | Not built. Article 32’s ministerial list is not bundled |
| Prescription capture | Manual and image. Labelled unverified | Electronic confirmation not built |
| Narcotic and psychotropic dispensing | Blocked unless the tenant enables controlled dispensing and fills the requirement matrix, including form number and max days | Schedule of Law 14 of 1995 is not bundled. Designated form is not issued by this software |
| Controlled custody register | Local ledger when enabled | EDE “register for controlled custody” is not filed by this software |
| Disposal of medical products | Local approval and document | EDE disposal authorization is not requested by this software |
| Recall | Local hold, trace, and status `NOT_REPORTED` | No notification to MOHAP, DHA, or DOH |
| Tatmeen 2D / GS1 scan | Barcode and GTIN stored and scanned as identifiers | No Tatmeen commissioning, shipping, or decommissioning messages |
| Insurance eligibility and claim | Manual claim, status `MANUAL_PENDING` | No payer |
| Drug interaction or clinical decision | Not a feature | Not a feature. The assistant refuses diagnosis, prescribing, and interaction claims |
| Adverse-event report (Article 46) | Not a feature in v1 | Not built |
| Advertising approval | Not a feature | Not built |
| Compounding, hospital clinical pharmacy, online pharmacy | Subtypes not offered | Out of scope |

Jurisdiction is a tenant setting so Dubai, Abu Dhabi, and the northern emirates are not forced through one hardcoded rule set. Changing jurisdiction does not import a new law. It only selects which local requirement rows the tenant must complete before restricted actions turn on.

## 12. Existing versus new

| Concern | Decision |
|---|---|
| Profile, capabilities, signup subtype, taxonomy seed | Extend the existing preset machinery. New profile `pharmacy`. Do not alias `grocery` |
| Category tree | Extend `categories` and `sub_categories`. Seed JSON. No third level |
| Sellable SKU, barcode, price, tax, variants, images, UOM | Reuse `products` and related tables |
| Generic name, class, ingredients, packs, price control | New `pharmacy_product_details` and `product_ingredients` |
| Dynamic cosmetic and device fields | Reuse attribute definitions. Do not extend `specifications.ts` keyword matching |
| Leaflets and registration files | New `product_documents` |
| On-hand, ledger, cost, allocations | Reuse inventory and batch tables |
| Manufacturer lot, quarantine, recall, strict FEFO | Extend `batch_items` and `batch_ledger` behind a policy branch |
| Purchase orders, suppliers, bills, payments | Reuse. Extend supplier with licence fields. Extend GRN with a lots array |
| Sales invoice, tax, tenders, loyalty, promotions | Reuse, with hooks that refuse restricted discounts and restricted offline lines |
| Manager approval | Reuse for price, floor, credit, and refund only |
| Prescription, verification, dispensing, duty | New |
| Pharmacist licence | New credential table. Not `employee_profiles.job_title` and not the role name |
| Patient clinical data | New tables. Customer row stays commercial |
| Insurance | New, manual |
| Cold chain and recall | New, holding the existing batch status |
| Returns | Reuse documents. Change restock default for pharmacy products |
| Audit | Reuse `audit_logs`. Add action types |
| Reports shell | Reuse report permissions and exports. Add pharmacy queries |
| Assistant | Reuse the tool runner. Add operational tools. No clinical tool |
| POS | Extend the Tauri register and its SQLite cache. No second app |
| Portal | Extend `apps/web` navigation. No second portal |
| Workflow engine | None exists. Prescription status is a dedicated state machine, not `ApprovalRequest` |

## 13. Migration plan

All migrations are Alembic revisions on the tenant database, after `20261118_0113`. They are additive. Existing profiles keep their rows and their FEFO behavior.

1. Profile registration is code (`capabilities.ts` and `capabilities.py`), not a data migration. Existing `business_settings.business_profile` values stay valid. No tenant is rewritten to `pharmacy`.
2. Category columns `display_order`, `is_active`, `image_key`, `product_kinds`, `form_policy`, and the subcategory order and active flags. Defaults: order 0, active true, empty kinds.
3. `pharmacy_product_details`, `product_ingredients`, `product_documents`, `substitution_groups`.
4. `batch_items` columns listed in section 6, default `lot_status = AVAILABLE`, `quantity_reserved = 0`. New movement types added in application code, not as a check that would reject old rows. `batch_movements`.
5. GRN lot capture is an API change. A nullable `goods_receipt_line_id` on `batch_items` is the only schema change. Old receipts leave it null.
6. Supplier licence columns, all nullable.
7. Prescription, credential, duty, verification, and dispensing tables.
8. Regulatory policy, controlled ledger.
9. Patients, allergies, insurance.
10. Storage locations, temperature readings, recalls.
11. Rebuild `products.search_text` to include generic name and GTIN when the details row exists. The generated column expression changes in this revision only, with a backfill that leaves non-pharmacy products identical.
12. SQLite cache columns on the register are an application migration in `db.rs` (`ALTER TABLE` the way `model_number` was added), not a server Alembic revision. Shipped in the same release as the POS stage, not before.

No migration drops a grocery column, tightens a grocery check, or changes `fefo_order` for products that have no pharmacy details.

Control-plane `ck_tenants_demo_business_type_known` is untouched until a demo tenant is deliberately added in Stage 10.

## 14. API plan

Routes stay under the existing `/v1` router, tenant-scoped, with the capability dependency pattern used by `expiry_router` (`module(Capability.FEFO)`).

| Area | Routes | Reuses |
|---|---|---|
| Catalog | `POST/PATCH /pharmacy/products`, ingredients, documents | Product create service, image upload, attribute values |
| Categories | Existing `/categories` plus the new fields | `category_service` |
| Lots | `GET /pharmacy/lots`, quarantine, release, damage, write-off | `move_stock`, `batch_ledger` |
| Receiving | Extend `POST` purchase-order receive with `lots` | `receive_purchase_order` |
| Prescriptions | CRUD, submit, verify, reject, list | Audit service |
| Dispensing | `POST /sales` gains an optional dispensing payload. The sale service rejects it unless the prescription checks pass | Sales, tax, tenders, loyalty |
| Patients | `/pharmacy/patients` | Customer link |
| Insurance | `/pharmacy/claims` manual transitions | Tenders for co-pay |
| Cold chain | `/pharmacy/storage-locations`, `/pharmacy/temperature-readings` | Batch quarantine |
| Recall | `/pharmacy/recalls`, match, affected sales | Batch status, allocations |
| Policy | `GET/PATCH /pharmacy/policy` | `module_settings` |
| Reports | `/pharmacy/reports/...` one route per report in section 16 | Existing export style |
| Assistant | New tool names registered in `TOOLS` | `assistant_tools.run` permission gate |

Dispensing is not a side door that writes stock without a sale. The sale is the financial document. The dispensing record is the clinical document. They commit together.

Idempotency: the register already sends an idempotency key. Dispensing uses that same key so a retry cannot dispense twice. The server stores the key on the sale, as current sync does, and returns the original sale.

## 15. POS and Business Pro

### Register (`apps/desktop`)

One register. Pharmacy mode is the capability set synced with the session, the same way grocery shows weighed items.

Sell screen adds, when `pharmacy_catalog` is on:

- Search by name, generic name, brand, SKU, barcode, GTIN
- Category filter from the tenant tree
- Line display: strength, dosage form, nearest eligible expiry, dispensing class, controlled marker
- Patient and prescription lookup for non-OTC lines
- Verification state on the line (missing, pending, approved)
- Cart, quantity in the selling unit, price, discount if the line allows it, tax, payment, receipt

OTC checkout: stock check uses sellable lot quantity, allocate strict FEFO, tax, pay, print.

Prescription checkout: block until prescription, remaining quantity, verification, and on-duty pharmacist are present. Then allocate and write the dispensing record.

Restricted checkout: block unless the controlled policy returns allow. There is no manager override button.

Receipt fields, each printed only when the tenant receipt policy marks it required: pharmacy name, licence number, transaction number, product, strength, quantity, lot and expiry, pharmacist name and licence, tax, payment. Patient name is off by default. Diagnosis and allergy are never printed.

Offline cache adds, for OTC products only: dispensing class, generic name, strength, form, `offline_policy`, sellable quantity, nearest expiry, and a recall watermark timestamp from the last successful sync. It does not cache prescription bodies or allergies.

Offline rules:

- `offline_policy = BLOCK`, or class other than OTC: the line cannot be added while offline.
- Recall watermark newer than the cache, or cache older than the tenant max-age: block every pharmacy line, including OTC.
- Queued OTC sales retry with the existing sync queue. The server re-runs strict FEFO. If the lot is no longer eligible, the sale is rejected and the register shows a conflict. It does not silently reassign a controlled lot.
- Duplicate prevention stays the idempotency key.

### Business Pro (`apps/web`)

New nav group `pharmacy`, hidden unless the profile is `pharmacy`. Items follow the existing `NavItem` permission and capability gates.

Dashboard. POS sales (link to the existing sales list, filtered). Medicine catalogue. Categories. Prescriptions. Patients. Dispensing history. Inventory and batches (the existing inventory screens, with lot status). Procurement, suppliers, purchase orders, GRN (existing screens plus lot capture). Returns. Controlled medicines. Insurance. Cold chain. Recalls. Reports. Staff and permissions (existing users, roles, plus credential editor). Pharmacy settings (regulatory policy, FEFO thresholds, receipt policy, offline policy).

Product create is a wizard that switches fields from `product_kind` and `form_policy` using the matrix in section 5.5. The detail page sections are: general, ingredients, strength and form, packaging, regulatory class, identifiers, lots, pricing, suppliers, storage, documents, stock history, sales history, audit. Sections the user cannot read are absent, not masked with empty clinical data.

Dates use `AxizDatePicker` and `DD-MM-YYYY`, stored as `YYYY-MM-DD`.

## 16. Reports and assistant

Dashboard KPIs, tenant- and permission-scoped: sales today, gross margin, OTC sales, prescription sales, prescriptions waiting, verifications waiting, low stock, near-expiry, expired, quarantined, lot discrepancies (on-hand versus sum of layers), supplier payables, claims in `MANUAL_PENDING`, returns, top medicines.

Reports:

1. Daily sales
2. Product sales
3. Category sales
4. Generic sales (group by `generic_name`, list the SKUs)
5. Brand sales
6. Prescription dispensing
7. OTC sales
8. Batch stock
9. Expiry, using the tenant thresholds
10. FEFO compliance (sales whose allocation was not the then-soonest eligible lot — should be empty if the allocator is the only writer)
11. Near-expiry valuation at cost
12. Expired stock
13. Controlled register
14. Stock movement
15. Purchase history
16. Supplier performance (lead time and fill from existing PO and GRN)
17. Gross margin
18. Returns
19. Recall trace
20. Cold-chain excursions
21. Insurance claims
22. Pharmacist activity
23. Audit and authorization history

Reports 6, 13, 19, 21, 22, and 23 require `reports:pharmacy`. Any column that identifies a patient also requires `reports:pharmacy_clinical`. A user with only `portal:reports_read` sees sales, stock, and expiry totals with no patient column.

Assistant tools, each with an existing or new permission, added in Stage 9:

- Expiring lots within N days
- Lots below a remaining-quantity threshold
- Dispensing count for a period, counts only, no patient rows
- Supplier bills outstanding (reuse `payables_due`)
- Top OTC products
- Stock movements for a period
- Lots matched to a recall reference

The system prompt for pharmacy tenants states that the assistant cannot diagnose, recommend a prescription medicine, prescribe, approve a prescription, authorize a controlled dispensing, override an allergy, or state a drug interaction. Tools do not expose a path that would do those things. If a question asks for them, the assistant refuses and points the user to the pharmacist.

## 17. Staged implementation

Each stage is releasable behind the new capabilities, default off for every existing tenant. A stage does not start until the previous stage’s tests are green. No pharmacy demo tenant before Stage 10.

| Stage | Build | Done when |
|---|---|---|
| 1 | This document | Reviewed. No code in this stage |
| 2 | Profile, taxonomy, details, ingredients, documents, data-driven forms, GTIN, search | A pharmacy tenant can create a tablet, a meter, a supplement, and a cosmetic with different fields. Grocery catalog tests unchanged |
| 3 | Lot columns, strict FEFO, thresholds, quarantine split, recall status, release | Two lots of one SKU sell soonest-expiry first. Expired and quarantined lots cannot sell. Grocery expired-last test still passes |
| 4 | Supplier licence, GRN lots, pending release, supplier return | Stock from a pharmacy GRN is not sellable until release. One PO line can receive two lots. Invoice link still works |
| 5 | Prescription, credential, duty, verification, dispensing transaction, audit | Cashier and manager-discount permissions cannot dispense. Manual prescriptions stay unverified. Partial and repeat quantities hold |
| 6 | Tauri register, cache, receipt, offline policy | OTC sells on the Windows register. Prescription lines follow Stage 5. Offline cannot sell a blocked class |
| 7 | Patients, insurance manual claims, cold chain, permissions on clinical reads | Excursion quarantines and does not auto-release. Claims stay `MANUAL_PENDING`. Customer exports omit allergies |
| 8 | Dashboard and the 23 reports | Permission splits hold. Existing profile dashboards unchanged |
| 9 | Assistant tools and adapter interfaces with no live authority | Operational questions answer from tenant data. Clinical questions refuse. Adapters have a manual implementation only |
| 10 | Migration rehearsal, regression, offline conflict tests, security pass, then a demo tenant | The acceptance list in the project brief passes, including unchanged results for the existing profiles |

Stage 2 and Stage 3 are the foundation. A prescription module on an unmodified product and an aggregate stock counter would have to be rewritten once lots exist. Stage 5 does not start before Stage 3 is enforcing strict FEFO on the server.

### Test obligations by stage

Catalog: every product kind, category seed plus a tenant-added subcategory, ingredients, unit factor, barcode and GTIN uniqueness, rejection of a medicine without strength or class.

Inventory: two lots, FEFO order, expired rejection, quarantine exclusion, recall exclusion, transfer of a lot, adjustment, grocery FEFO regression, sync conflict when the server lot is no longer eligible.

Procurement: partial receipt, two lots on one line, missing expiry rejected, pending release, bill still matches the GRN, supplier return.

Prescriptions: valid, expired, missing prescriber, missing patient, OTC without a prescription, partial, repeat, quantity above remaining, cashier rejected, credential expired rejected, audit row written.

Controlled: flag off rejects release, missing special-form field rejects, handover writes two entries, adjustment without permission rejects.

POS: OTC, prescription, restricted, barcode, refund lands in quarantine, offline block. These hit the API, not only a mocked register.

Regression: capability mirror test, grocery receive-without-lots, fashion variants, restaurant checkout, electronics serial sale.

## 18. Acceptance mapping

The brief’s 23 acceptance checks land in the stages above. None of them is met by this document alone. After Stage 10, pharmacy is a selectable profile with its own taxonomy and medicine master, lots and strict FEFO, procurement that holds stock until lot release, prescription and pharmacist checks that a discount permission cannot skip, recall trace, separated patient data, returns that do not restock medicines by default, cold-chain records, pharmacy reports, the existing Windows register, Business Pro screens, explicit offline blocks, and unchanged existing profiles.

## 19. Open points for review

1. Confirm v1 subtype is only `community_pharmacy`.
2. Confirm official price, when the tenant has not entered one, blocks the sale rather than allowing a retail price with a warning.
3. Confirm OTC offline sales are in v1, with server-side FEFO on sync, and that every other class is online-only.
4. Confirm pack conversion stays a single factor to the base unit, not a carton → box → strip graph.
5. Confirm veterinary stays in the seed but inactive.
6. Name the compliance reviewer who will sign the regulatory matrix before Stage 10.
