# Pharmacy Stage 3A — Stock Lots, Expiry, and Strict FEFO

Status: design only. Stage 2 catalogue is accepted. Nothing in this document has been implemented.

This stage extends the existing inventory ledger. It does not add a second product master, a second stock quantity, or a second allocation engine.

Governing locks from Stage 1 still apply:

- `products` remains the product master. Manufacturer lot and expiry are not product fields.
- `batch_items.quantity_remaining` remains the only lot quantity.
- `inventory_levels` remains branch on-hand and reserved.
- `stock_movements` remains the append-only ledger. `services.inventory.move_stock` is the only production writer of on-hand.
- `batch_allocations` remains the record of which layer a movement drew.
- Grocery FEFO, `EXPIRED_STOCK_SOLD`, grocery receiving, and the seven existing profiles stay as they are.
- `PurchaseBatch.batch_number` is a receipt document number. It is not a manufacturer lot. Existing grocery batch numbers are not backfilled into a lot field.

Alembic tenant head at the time of this audit: `20261118_0114` (parent `20261118_0113`). No migration is created here.

## 1. Existing inventory architecture

Stock of one product at one branch lives on `inventory_levels`:

- `quantity_on_hand` — physical units. Check `>= 0`.
- `quantity_reserved` — units promised to a transfer, quote, sales order, repair, or rental. Check `>= 0`.
- `available` — `quantity_on_hand - quantity_reserved`. Not stored.

`stock_movements` is append-only. `quantity` is signed. `quantity_after` is the branch on-hand after the row. Movement types in production: `PURCHASE_IN`, `SALE_OUT`, `RETURN_IN`, `TRANSFER_IN`, `TRANSFER_OUT`, `DAMAGE_SHRINKAGE`, `AUDIT_ADJUSTMENT`, `PURCHASE_REVERSAL`, `RECIPE_OUT`.

Cost layers are `purchase_batches` plus `batch_items`. One receipt document holds many product lines. Each line stores `quantity_imported`, `quantity_remaining`, unit cost, selling price, and an optional `expiry_date`. Checks: imported and remaining are non-negative, remaining never exceeds imported, costs are non-negative. There is no manufacturer lot, manufacture date, quarantine, recall, or release column.

`batch_allocations` links one movement to one layer: `quantity`, `unit_cost_cents`, `expired`, and later `sale_item_id` and `quantity_returned`. `sale_items.batch_item_id` points at the first layer of a split. The full split is the allocation rows, not that single foreign key.

Tenant isolation: `20261024_0071` adds `tenant_id` to `batch_items` and `batch_allocations`, forces row-level security, and applies `tenant_isolation`:

```text
USING (tenant_id = current_setting('app.tenant_id') OR app.bypass_rls = 'on')
WITH CHECK (same)
```

Application queries also run inside the tenant session. A new pharmacy table follows the same pattern.

Locking: `_locked_level` and `batch_ledger._open_items` add `FOR UPDATE` only when the dialect is PostgreSQL. SQLite tests do not row-lock. That is existing behavior and must stay, with pharmacy concurrency tests running on PostgreSQL.

`record_sale` does not commit. The caller (`sync_service` for the register, the portal sale route for Business Pro) owns the transaction. A `SyncRejected` or `ApiError` rolls the session back, so a failed allocation does not leave a half-posted sale.

## 2. `batch_items` lifecycle and call graph

### Who changes `quantity_remaining`

| Writer | What it does | Grocery-safe to extend |
|---|---|---|
| `batch_ledger._draw` | Decrements remaining, inserts `BatchAllocation`, sets `expired` | Yes. Pharmacy adds a filter before this runs. The decrement stays here. |
| `batch_ledger._restore_serial` | Adds 1 back and increments `quantity_returned` | Yes. Serial path. Pharmacy medicines are not serialized units. |
| `batch_ledger.restore_sale_item` | Puts a return back onto the layers the sale drew, newest allocation first | Yes for the quantity. Pharmacy adds a status change after the restore. |
| `cost_layers.record_receipt_layer` | Inserts a layer at the received quantity. No expiry, no lot | Yes. Pharmacy fills lot fields on the new row for lot-controlled products only. |
| `cost_layers.record_adjustment_layer` | Inserts a layer. Writes the operator's `lot_number` into `purchase_batches.batch_number` (32 characters, tenant-unique) and may set `expiry_date` | Do not reuse `batch_number` as the manufacturer lot. Pharmacy writes a real lot column. The existing adjustment path stays for non-pharmacy products. |
| `import_batch_service` commit | Inserts lines and calls `move_stock` `PURCHASE_IN` | Yes. Spreadsheet expiry already lands on `expiry_date`. Manufacturer lot is a new mapped column, not the file's receipt number. |
| `import_batch_service._correct_quantity` | Adjusts imported and remaining together, with a ledger row | Yes. |
| `import_batch_service.rollback` | Draws the reversible quantity through `move_stock`, then sets remaining to 0 | Leave this path alone. It is receipt reversal, not a pharmacy rule. |
| `trade_in_service` | Creates a one-unit layer and later zeroes it | Electronics. Do not treat it as a medicine lot. |
| `onboarding_service` demo rewind | Adds allocation quantity back and deletes movements | Demo only. Not a pharmacy path. |

`move_stock` is the single production decrement of on-hand. After it inserts the movement it calls `batch_ledger.on_movement`:

- Positive quantity and no serial: the movement does not create a layer. The caller that received goods creates the layer itself.
- Negative quantity: `_consume` draws open layers. If `Capability.FEFO` is on, order is `fefo_order`. Otherwise FIFO by `created_at`, `position`, `id`.
- An optional `batch_item_id` is sorted first. Expiry write-off, waste, and batch rollback pass it so the named line is drawn.
- When nothing remains on open layers, further units come from unlayered stock (opening balances, a transfer-in that never opened a layer). `sum(quantity_remaining)` is allowed to be less than or equal to on-hand. It must not exceed on-hand.

### Callers of `move_stock` that therefore change layers

| Caller | Movement | Transaction | Lot today |
|---|---|---|---|
| `sale_service.record_sale` | `SALE_OUT` per product, then `link_sale` | Caller commits once | FEFO/FIFO. Expired still sells. `EXPIRED_STOCK_SOLD` audit on `SALE_OUT`. |
| `inventory.receive_purchase_order` | `PURCHASE_IN`, then `record_receipt_layer` | `db.commit` in the GRN | New layer. `batch_number` is `{GRN}-{line}`. No lot, no expiry. |
| `import_batch_service` commit | `PURCHASE_IN` | Commit after the batch | Layer created before the movement. Expiry copied from the file. |
| `inventory.ship_transfer` | `TRANSFER_OUT` after `release` of the product reservation | Commit on ship | Draws layers at the source. Does not record which lot the UI chose. |
| `inventory.receive_transfer` | `TRANSFER_IN` | Commit on receive | Increases destination on-hand. Does **not** open a destination layer. Lot identity stops at the source. |
| `inventory.manual_adjust` | `AUDIT_ADJUSTMENT` or `DAMAGE_SHRINKAGE` | Commit in the adjustment | Additions open an adjustment layer. Removals draw FEFO/FIFO. |
| `expiry_service.write_off` / `record_waste` | Shrinkage or adjustment, `batch_item_id` set | Commit | Named line only. Write-off requires the line to already be past `expiry_date`. |
| `returns_service` | `RETURN_IN` then `restore_sale_item` when the condition policy says restock | Caller commits | Quantity returns to the original layers. Status is not changed because status does not exist. |
| `recipe_service` / `fnb_service.consume_sale` | `RECIPE_OUT` | Same sale transaction | Ingredients, not pharmacy packs. Unchanged. |
| `stock_count_service` | Adjustment to the counted quantity | Commit in the count | Draws or adds like a manual adjustment. |
| `sync_service` | Delegates to `record_sale` or `move_stock` for stock events | One sync transaction per event | Same rules as the live sale. |
| `transition_serial` | ±1 for IMEI status changes | Caller's transaction | Serial line, not a medicine pack. |

Purchase invoices do not move stock. `payables_service.create_bill_from_receipt` and `_create_bill_from_batch` create a supplier bill against a GRN or a purchase batch that has already booked inventory.

Reservations do not touch `batch_items`. `inventory.reserve` / `release` change only `inventory_levels.quantity_reserved`. Callers: transfer create, quotes, sales orders, repair workshop, fashion rental. A sale already refuses when `available` is short (`sale_service` around the demand check, and `move_stock` again). That blocks oversell at product level. It does not pin a specific lot.

### Grocery FEFO, which pharmacy must not edit in place

`Capability.FEFO` is on for grocery and for pharmacy. `open_items` calls `fefo_order` whenever that capability is on:

1. Dated and not expired (`expiry_date >= today`) — key 0, earliest expiry first.
2. No expiry date — key 1.
3. Expired — key 2, still drawn when nothing fresher remains.

`_flag_expired_sale` writes an `EXPIRED_STOCK_SOLD` audit when a `SALE_OUT` allocation has `expired=true`.

Stage 3 does not change `fefo_order` or `_flag_expired_sale`. A pharmacy-strict branch runs only for lot-controlled products and returns before those two functions. Every other product, including a non-medicine sold by a pharmacy tenant and every product at the other seven profiles, keeps today's order.

### What cannot support pharmacy lots without a new field

- `purchase_batches.batch_number` is tenant-unique and 32 characters. Two products cannot share one manufacturer lot code there. A GRN number is not a lot. Manual adjustment already overloads this column. Leave it.
- `products` has no lot or expiry. `ProductOut` does not expose `generic_name`, GTIN, or pharmacy details. Stage 3A does not add them.
- Transfer receive drops lot identity. A pharmacy transfer of a medicine is unsellable under strict FEFO until a destination layer exists. That layer is specified in section 7. It is not built here.
- The register caches one `stock_quantity` per product. It cannot prove expiry, quarantine, recall, or release.

## 3. Proposed database design

One new tenant migration, child of `20261118_0114`. Additive. No backfill of lot numbers or expiry dates. No update of `quantity_remaining`, `quantity_imported`, or `inventory_levels`.

### Columns on `batch_items`

| Column | Null | Meaning |
|---|---|---|
| `manufacturer_lot` | yes | Manufacturer lot code. Null on every existing row and on every grocery receipt. |
| `manufactured_on` | yes | Manufacture date. |
| `lot_status` | yes | Null means "not a pharmacy lot". The grocery allocator ignores it. |
| `quarantine_reason` | yes | Required by the application when status becomes `QUARANTINED`. |
| `recall_id` | yes | FK to `pharmacy_recalls` when status is `RECALLED`. |
| `recall_reason` | yes | Copy of the reason at the moment of the match, so a later edit of the recall header does not rewrite history. |
| `released_at` | yes | Timestamp of the release that made the row `RELEASED`. |
| `released_by_id` | yes | User who released. Not a licence check. Stage 1's pharmacist credential is a later stage. |
| `source_batch_item_id` | yes | Set on a transfer-in layer. Points at the source line in the same tenant. |

`expiry_date` already exists and stays nullable. Grocery rows keep whatever expiry they already have. Pharmacy does not invent one.

`lot_status` values, application-checked:

`RELEASED`, `UNRELEASED`, `QUARANTINED`, `RECALLED`, `DAMAGED`, `SUPPLIER_RETURN`.

Null is not a synonym of `RELEASED`. A null status is invisible to the strict allocator (ineligible) and invisible to grocery rules (grocery does not read the column).

Checks:

- `manufactured_on` is null or `<= expiry_date` when both are set.
- `manufacturer_lot`, when set, is 1–64 characters after trim. Stored trimmed.
- Status in the list above or null.
- `recall_id` is not null when status is `RECALLED`.
- No check that forces a lot number onto old rows.

Unique: `(tenant_id, product_id, manufacturer_lot, expiry_date)` is **not** unique. The same manufacturer lot can arrive on two GRNs and must remain two cost layers (two costs). Identity of a sellable slice is `batch_items.id`. A non-unique index `(tenant_id, product_id, manufacturer_lot)` supports recall matching.

Index for the strict draw, added beside the existing `ix_batch_items_fifo`:

`(tenant_id, product_id, store_id, lot_status, expiry_date, quantity_remaining)`.

### `batch_item_events`

Append-only. Current status stays on `batch_items` so allocation can filter without replaying history. The event row is the audit.

Columns: `id`, `tenant_id`, `batch_item_id`, `action` (`RECEIVED`, `RELEASED`, `QUARANTINED`, `RECALLED`, `DAMAGED`, `TRANSFER_OUT`, `TRANSFER_IN`, `RETURNED`, `SUPPLIER_RETURN`), `from_status`, `to_status`, `reason`, `recall_id`, `user_id`, `created_at`.

No quantity column. Quantity changes remain on `stock_movements` and `batch_allocations`.

RLS: same `tenant_isolation` policy as `batch_items`.

### `pharmacy_recalls` and `pharmacy_recall_lots`

`pharmacy_recalls`: `id`, `tenant_id`, `reference` (tenant-unique), `source_text`, `severity`, `reason`, `status` (`OPEN`, `CONTAINED`, `CLOSED`), `opened_by_id`, `created_at`. No regulator status and no outbound notification.

`pharmacy_recall_lots`: `recall_id`, `product_id`, `manufacturer_lot`, optional `batch_item_id`. Matching sets every open layer of that product and lot to `RECALLED` and writes an event. Closing a recall does not auto-release stock.

### What is deliberately absent

- No quantity on the new tables.
- No lot or expiry on `products` or `pharmacy_product_details`.
- No second ledger.
- No change to `ProductOut` or the POS SQLite schema in this stage. Section 9 says what a later stage would need if selective offline blocking is approved.

### Historical rows

Existing `batch_items` stay valid. New columns are null. Their `expiry_date` is unchanged. Grocery allocation reads the same columns it reads today. A pharmacy tenant that already holds stock received under Stage 2 has null `lot_status`. Under strict rules those units are not sellable until a user records a real lot and expiry and releases the layer. The migration does not guess those values.

## 4. Pharmacy lot lifecycle

Lot control applies only when all of these are true:

- The tenant has `Capability.PHARMACY_CATALOG` and `Capability.FEFO` (the pharmacy preset already has both).
- The product has a `pharmacy_product_details` row.
- `product_kind` is `MEDICINE`.

Other kinds at a pharmacy (`DEVICE`, `SUPPLY`, `PERSONAL_CARE`, shelf lines with no pharmacy row) keep today's FEFO. This is an explicit product test inside `_consume`, not a change to the capability flag. Turning FEFO off for the tenant would change nearest-expiry display and non-medicine draws. That is rejected.

Which non-medicine kinds must also be lot-controlled is an open decision (section 14). The default is medicine only.

Lifecycle of a medicine layer:

1. **Receive.** GRN or batch import creates the `batch_items` row as today, and also sets `manufacturer_lot`, `manufactured_on`, `expiry_date`, and `lot_status=UNRELEASED`. An event `RECEIVED` is written. On-hand still moves only through `move_stock`. The layer quantity still equals the received quantity.
2. **Release.** A later action sets `RELEASED`, `released_at`, `released_by_id`, and writes `RELEASED`. Until that happens the layer is not allocated. Who may release is not decided (section 14). The permission name in Stage 1 is `inventory:release_batch`. This stage does not treat a manager PIN or `ApprovalRequest` as a pharmacist licence.
3. **Quarantine.** Status `QUARANTINED`, reason required, event written. Remaining quantity is unchanged. The layer drops out of allocation.
4. **Recall.** Match on product plus `manufacturer_lot` sets `RECALLED`. Remaining quantity is unchanged so the units can still be counted, returned to the supplier, or written off.
5. **Damage.** Status `DAMAGED`, then the existing write-off path (`move_stock` with `batch_item_id`) reduces quantity. Status is not a substitute for the ledger.
6. **Transfer.** Source draw uses the same strict filter. Destination receive opens one new layer with `source_batch_item_id`, the same lot and dates, quantity equal to the units received, and status `UNRELEASED`. Same-tenant "copy RELEASED across" is not assumed. Section 14 records the question.
7. **Sale.** Strict FEFO draws only `RELEASED` layers. Allocations and `link_sale` are unchanged.
8. **Customer return.** Quantity is restored onto the original layer for cost history, then status is set to `QUARANTINED` with reason `RETURN_PENDING_RELEASE`. It is not sold again until a new release. This applies to lot-controlled products only. Grocery restock is unchanged.
9. **Supplier return.** Status `SUPPLIER_RETURN` and a negative ledger movement for the units sent back. The supplier bill credit stays in payables. No new purchasing engine.

Manual stock additions of a medicine use the same fields as a receipt. They do not write the lot into `batch_number`. `record_adjustment_layer` stays for products that are not lot-controlled, including its current `lot_number` → `batch_number` behavior.

Missing lot or missing expiry on a medicine receipt is a validation error. The receipt is rejected. The row is not saved half-filled.

## 5. Stock eligibility matrix

Evaluated in this order for a lot-controlled product. The first failing row rejects the layer. There is no override in this design. A row marked "confirm" needs a pharmacist or regulatory decision before any exception exists.

| Condition | Eligible | Allocation | Override | Who | Audit |
|---|---|---|---|---|---|
| `lot_status` is null | No | Reject the layer. If the sale still cannot be filled, reject the sale | No | — | None until a user records a lot and releases |
| `UNRELEASED` | No | Reject the layer | No. Release is the forward action, not a sale override | Confirm. Proposed permission `inventory:release_batch`. Not a manager PIN | `batch_item_events` `RELEASED` |
| `QUARANTINED` | No | Reject the layer | No | Confirm before anyone may clear quarantine | Event `QUARANTINED` and a later `RELEASED` if a release is later allowed |
| `RECALLED` | No | Reject the layer | No | Confirm. Closing a recall does not release stock | Event `RECALLED` plus `pharmacy_recalls` |
| `DAMAGED` or `SUPPLIER_RETURN` | No | Reject the layer | No | Existing inventory adjust / write-off permissions | Ledger movement plus event |
| `expiry_date` null | No | Reject the layer | No | A receipt without expiry is rejected up front | Receipt validation error |
| `expiry_date < today` (store date, UTC date as `batch_ledger.today` does today) | No | Reject the layer. Do not draw it. Do not write `EXPIRED_STOCK_SOLD` | No | Confirm if a jurisdiction allows an expired sale. This design does not | None on the sale, because the sale does not happen |
| `manufactured_on` after `expiry_date` | No | Row cannot be saved | No | — | Validation error |
| `quantity_remaining <= 0` | No | Skip. Not an error by itself | No | — | — |
| Product `is_active` false | No | `record_sale` already rejects the product | No | — | Existing inactive message |
| Product reserved at branch (`available` short) | The sale is rejected | Existing `available` check. Lots are not reserved individually | No | — | Existing insufficient-stock rejection |
| Held by another open sale in the same transaction | The second transaction waits on `FOR UPDATE` or sees a lower remaining | Reject if still short after the lock | No | — | — |

Reserved stock is enforced at `inventory_levels`, not by a second quantity on the lot. That can undersell (the earliest lot is the one a transfer reserved only at product level, so a walk-in sale fails even though a later lot looks free). It cannot oversell. Lot-level holds are not in Stage 3. They would have to stay equal to `quantity_reserved` and are deferred until a quote must pin a specific lot.

Default safety, locked: expired, quarantined, recalled, and unreleased stock cannot be sold.

## 6. Strict FEFO algorithm

New function `pharmacy_lots.strict_order`, called from `batch_ledger._consume` only when the product is lot-controlled. `fefo_order` is not modified.

1. Load open layers for the product and store with the existing `FOR UPDATE` on PostgreSQL.
2. Split off every layer that fails section 5. Those rows are not sorted and not drawn.
3. Sort the eligible layers by `expiry_date` ascending, then `created_at`, then `id`.
4. If their `quantity_remaining` sums to less than the movement, raise `SyncRejected` ("Not enough released stock of {product} before expiry") and draw nothing.
5. Otherwise call the existing `_draw` until the movement is filled. One sale line may consume several lots. That is a full fill of the requested quantity, not a partial sale.
6. Do not call `_flag_expired_sale` on this path. An expired layer never enters the candidate list, so the audit cannot fire for a medicine.
7. `link_sale` still runs after the sale items exist and stamps `sale_item_id` on each allocation. `sale_items.batch_item_id` remains the first layer. Recall reports use the allocation rows, not that single column.

Unlayered stock (on-hand with no layer) is not a pharmacy fallback. If eligible layers are short, the sale fails even if `quantity_on_hand` is higher. That is the safe side of the existing "unlayered stock is sold last" rule, and it applies only to lot-controlled products. Grocery still sells unlayered stock after its layers.

Partial allocation across lots is allowed. Partial allocation of the requested quantity is not. The sale is one transaction, so a failure on line 2 rolls back line 1's draws.

Concurrent checkout: both sales lock the branch `inventory_levels` row, then the open `batch_items` rows. PostgreSQL serializes them. The second sale sees the first sale's remaining quantity or waits. SQLite tests cannot prove this. The concurrency test belongs on disposable PostgreSQL.

Two registers selling the last units of one lot: the same locks. One commit wins. The other gets `SyncRejected` and must not record a local completed sale.

## 7. Transaction and concurrency strategy

`record_sale` already does demand check, `move_stock` (which draws layers), sale insert, and `link_sale` before the caller commits. Strict FEFO stays inside `_consume`, so it is in that same transaction. No outbox, no "allocate now, post later".

Idempotent sync: `record_sale` already rejects a replay of the same sale id. A replay must not draw a second time. That existing guard stays.

Transfer of a medicine, same transaction boundaries as today, plus one extra insert on receive:

- Create transfer: `reserve` at product level only. Unchanged.
- Ship: `release`, then `TRANSFER_OUT`. For a lot-controlled product, `_consume` uses strict order. The allocations name the source lots.
- Receive: `TRANSFER_IN` increases destination on-hand, then one new `batch_items` row per source allocation, quantity equal to the allocated units, `source_batch_item_id` set, status `UNRELEASED`, same manufacturer lot and dates. No second on-hand change. Non-medicine transfers do not gain this row.

If the destination layer insert fails, the receive transaction rolls back and the source has not been committed as received.

Reservation expiry stays the existing quote and sales-order release. It does not expire a lot. Lot expiry is a date filter at draw time, not a background job that changes quantity.

Background jobs that exist today (`expiry_service` alerts, write-off) stay. A new job must not auto-release, auto-recall, or rewrite grocery layers.

## 8. Returns and recall traceability

Chain, all existing tables plus the new status and recall rows:

Supplier → purchase order → `goods_receipts` → `purchase_batches` (`goods_receipt_id`, `supplier_id`) → `batch_items` → `stock_movements` via `batch_allocations` → `sale_items` → `sales` (`customer_id`, `invoice_number`, `device_id`).

A recall report, tenant-scoped:

- Input: product and `manufacturer_lot`, or a `pharmacy_recalls.id`.
- Remaining stock: `batch_items` with that lot and `quantity_remaining > 0`, any status.
- Block: set those rows to `RECALLED`. Do not change quantity.
- Sales: `batch_allocations` joined to `sale_items` and `sales` where `batch_item_id` is one of the matched layers and `sale_item_id` is not null. Include splits. Do not use only `sale_items.batch_item_id`.
- Returns: `batch_allocations.quantity_returned` and `return_items` for those sale lines. A return that restored quantity does not make the layer sellable, because status is `QUARANTINED` or `RECALLED`.
- Transfers: destination layers with `source_batch_item_id` in the matched set. Those destinations are recalled too, in the same tenant.
- History: `batch_item_events` plus `audit_logs` for the recall header.

The report lists affected invoices. It does not notify a regulator, mark a submission, or claim a MOHAP, DHA, or DOH integration.

Customer return of a medicine uses the existing return document. Restock still calls `restore_sale_item` so cost returns to the original layer, then the layer is quarantined. A condition of "resellable" does not set `RELEASED`. Refund tenders stay on the existing return path.

Purchase return of unsold units uses `PURCHASE_REVERSAL` or a shrinkage movement with `batch_item_id`, and sets `SUPPLIER_RETURN`. Grocery batch rollback is not retargeted.

## 9. POS online and offline compatibility

The Tauri register, inspected and not modified:

- `ProductOut` has no pharmacy object, no generic name, no GTIN, no lot, no expiry eligibility.
- SQLite `products` stores one `stock_quantity`. Search haystack is name, model, barcode, SKU, category, brand, season, collection. Offline search cannot see generic name. That limit is accepted from Stage 2.
- Online search merges `GET /api/v1/products/search`, which can match `generic_name` through `search_text`.
- Checkout queues a sale and `sync` posts it to `record_sale`. The server is where stock is drawn.
- Local stock is a cache. Refresh falls back to the cache when the API is down.

Online pharmacy checkout can use the existing register. The sale post runs strict FEFO. If the server rejects, the register already treats a sync rejection as a failed event. No new product field is required for the online path. The cashier does not pick a lot. The server records the lots on `batch_allocations`.

Offline cannot be safe for a lot-controlled product:

- The cache has no lot, no expiry, no quarantine, no recall, no release.
- A successful offline sale would commit on the register and might later be rejected, or worse, accepted against stock that was recalled after the cache was built.
- Stage 1 forbids a cached quantity from overriding a recall or quarantine watermark.
- Stage 2 stores `offline_policy` `ALLOW` or `BLOCK` on the pharmacy extension. Default for a new medicine is `BLOCK`. This stage does not change that column and does not approve a new OTC offline rule.

Fail-closed behavior, proposed for implementation only after approval:

- While the register's enabled capabilities include `pharmacy_catalog` and the API cannot be reached, the till refuses to complete a sale that contains a stocked line. It does not queue it.
- That blocks shelf lines at a pharmacy too, because the cache cannot tell a medicine from a soap bar without a new `ProductOut` field.
- A narrower rule (block only medicines) needs one boolean on `ProductOut`, for example `requires_online_stock_check`, and a column on the SQLite cache. Stage 2 locked `ProductOut`. Stage 3A does not add it. It is an approval item in section 14.
- If that boolean is later approved, `offline_policy = ALLOW` still does not authorize an offline medicine sale. Lot eligibility cannot be checked offline. `ALLOW` remains a catalogue flag until a separate OTC decision says otherwise.

An offline queue that already contains a pharmacy sale from an older register build is rejected at sync when strict FEFO cannot fill it. The event stays failed. It is not retried into an expired or recalled lot.

`nearest_expiry` on the product payload, already computed as the minimum dated open layer when FEFO is on, is a display hint. It is not permission to sell. It can point at an expired or unreleased layer. The register must not treat it as eligibility.

## 10. Tenant isolation

- New tables are `TenantScoped`, with `tenant_id` not null, an index, and the `20261024_0071` policy on PostgreSQL.
- `manufacturer_lot` indexes include `tenant_id`. Lots are not unique across tenants and not unique within a tenant.
- Recall matching filters `product_id` and `tenant_id`. A lot code in tenant A does not recall tenant B.
- `source_batch_item_id` is an intra-tenant foreign key. Transfers do not cross tenants today.
- RLS tests belong with `tests/test_rls_postgres.py` on disposable PostgreSQL: a session set to tenant A cannot select tenant B's `batch_item_events` or recalls.
- Application code keeps using the tenant session. RLS is the backstop, not the only filter.

## 11. Migration and rollout

Revision id, when implementation is approved: `20261118_0115`, `down_revision = 20261118_0114`. Tenant schema only. The control-plane migration head is not part of this change.

Upgrade:

- Add the nullable columns and checks on `batch_items`.
- Create `batch_item_events`, `pharmacy_recalls`, `pharmacy_recall_lots`.
- Enable and force RLS on the new tables on PostgreSQL.
- Do not `UPDATE` existing `batch_items`. Do not set a status. Do not copy `batch_number` into `manufacturer_lot`. Do not copy a grocery expiry into a fabricated lot.

Downgrade exists in the file so a disposable database can be reset. It drops the new tables and columns. It is not the production rollback.

Production rollback plan:

- Ship the application change behind the lot-controlled branch. A deploy of the previous application ignores unknown columns and new tables.
- Grocery code paths never read the new columns.
- If a defect appears, redeploy the previous application. Leave the columns in place. Do not run Alembic downgrade on a production tenant.
- A forward fix is the way to correct a bad release. Deleting the columns would be a later planned migration, not an incident response.

Rollout order:

1. Migrate a disposable PostgreSQL database from `0114` to `0115` and back. Drop the database. Do not touch a persistent tenant.
2. Confirm grocery quantities and `EXPIRED_STOCK_SOLD` on that database before the downgrade.
3. Deploy schema before the application that writes the columns.
4. Pharmacy receiving starts writing `UNRELEASED` only after the application is live. Old layers stay null and unsellable for medicines until a person releases them with a real lot and expiry.
5. Turn the strict branch on only for `MEDICINE`. Watch for sales that previously succeeded against expired grocery-style FEFO at a pharmacy tenant. Those sales will start failing. That is the intended safety change, and it is pharmacy-only.

SQLite test databases use `create_all`. Models must match the migration. Tests do not run Alembic history (it already fails earlier on UUID hex).

## 12. API and UI design

No routes are added in Stage 3A. Proposed for 3B, all under the existing pharmacy and inventory permissions:

| Action | Proposed route | Notes |
|---|---|---|
| Release a layer | `POST /api/v1/pharmacy/lots/{batch_item_id}/release` | Body: reason. Sets `RELEASED`. Rejects recalled and damaged rows. |
| Quarantine | `POST /api/v1/pharmacy/lots/{batch_item_id}/quarantine` | Body: reason, required. |
| Open a recall | `POST /api/v1/pharmacy/recalls` | Matches lots, blocks remaining, returns the affected-sale count. |
| Affected sales | `GET /api/v1/pharmacy/recalls/{id}/sales` | Tenant-scoped. Paginated. |
| Eligible quantity | `GET /api/v1/pharmacy/products/{id}/availability?store_id=` | Sum of released, in-date remaining at the store. Not a new quantity store. |

GRN receive gains optional `manufacturer_lot`, `manufactured_on`, and `expiry_date` on the line when the product is a medicine. They are required for medicines and ignored for other products. The receipt number stays the document number.

Business Pro, later, not in this stage:

- Receiving form: lot, manufacture date, expiry on medicine lines.
- Stock batch list: status, lot, expiry, release and quarantine actions.
- Recall screen: reference, lot, affected invoices. No "notify regulator" button.
- Product master: no lot field. The Stage 2 sentence stays: lot and expiry are stock-batch facts.

The register UI does not gain a lot picker.

## 13. Regression test matrix

| Case | Expected |
|---|---|
| Medicine receipt with lot, manufacture date, expiry | Layer `UNRELEASED`, on-hand increased once, event `RECEIVED` |
| Medicine receipt without lot | 422, no layer, no on-hand change |
| Medicine receipt without expiry | 422 |
| Manufacture date after expiry | 422 |
| Expired `RELEASED` layer | Sale rejected, remaining unchanged, no `EXPIRED_STOCK_SOLD` |
| Quarantined layer | Skipped. Sale fails if nothing else is released |
| Recalled layer | Skipped. Sale fails |
| Unreleased layer | Skipped. Sale fails |
| Two released lots | The earlier expiry is drawn first. The later lot is touched only for the remainder |
| Sale larger than the earliest lot and within the sum | Two allocations, one sale line, `link_sale` stamps both |
| Sale larger than the sum of eligible lots, even if expired or on-hand is higher | `SyncRejected`, transaction rolled back, no sale row |
| Two concurrent sales of the last units | One succeeds, one fails. PostgreSQL test |
| Return of a medicine | Quantity restored, status `QUARANTINED`, not sold again |
| Recall | Remaining layers `RECALLED`, sales listed, including a split allocation that was not `sale_items.batch_item_id` |
| Tenant B cannot read tenant A's recall | RLS test |
| Grocery dated, undated, expired | Order stays 0, 1, 2. Expired still sells. `EXPIRED_STOCK_SOLD` still written |
| Grocery `batch_number` | Not copied to `manufacturer_lot` |
| Electronics, wholesale, fashion, restaurant, cafe, quick service | Existing sale, receive, and stock tests pass with no new status required |
| Pharmacy non-medicine (no details, or kind other than `MEDICINE`) | Today's FEFO, including expired-last |
| Offline register with `pharmacy_catalog` and no API | Sale is not queued. Specified once the fail-closed register change is approved |
| Sync of a sale the server cannot allocate | Event rejected, layers unchanged |

Existing suites to run again, unchanged in intent: `test_grocery.py`, `test_inventory.py`, `test_capabilities.py`, `test_pharmacy_catalog.py`, `test_product_search.py`. New tests live in `tests/test_pharmacy_lots.py` and a PostgreSQL concurrency and RLS module. They are not written in this stage.

## 14. Unresolved business and regulatory decisions

These are not invented here. Implementation of the happy path can wait on them only where the row says so.

| Decision | Default used in this design | Blocks 3B? |
|---|---|---|
| Who may release a layer, and is a pharmacist licence required? | No sale override. Release is a separate action. Stage 1 permission name is a placeholder, not a licence check | Yes, before the release endpoint is built |
| May quarantine be cleared, and by whom? | No sale of quarantined stock. No clear action specified | Yes, before a "lift quarantine" action |
| May anyone sell expired stock with a signature? | No | No. The rejection is the design |
| Are `DEVICE`, `SUPPLY`, supplements, or cosmetics lot-controlled? | Only `MEDICINE` | No. Kinds can be added later without a schema change |
| After an intra-tenant transfer, is the destination `RELEASED` or `UNRELEASED`? | `UNRELEASED` | No. The safe default is specified. A later setting can copy status |
| May OTC with `offline_policy=ALLOW` sell offline? | No. The flag is not changed. Offline lot checks cannot be done | Yes, before any register change. Needs an explicit OTC decision |
| Is a blanket offline block for every stocked line at a pharmacy acceptable, or is one `ProductOut` boolean approved? | Design prefers the boolean. Stage 3A does not add it. Until then the safe register behavior is to block all stocked sales while offline | Yes, before register work |
| Does a customer return of OTC ever restock straight to `RELEASED`? | No. Quarantine, then a release if one is later allowed | No |
| Controlled-drug register, prescriptions, dispensing, insurance | Out of scope. A recalled or unreleased layer is already unsellable, which matches Stage 1's "controlled products stay `PENDING_RELEASE` until that module exists" | No for Stage 3 |
| Expiry timezone | Use the date `batch_ledger.today` already uses (UTC). A store-local date is a later change and would affect grocery if applied inside `fefo_order` | No. Do not change grocery's clock |

## 15. Stage 3 implementation sequence

Do not start until this document is approved.

1. Migration `20261118_0115` on a disposable database only. Upgrade, grocery regression, downgrade, drop the database.
2. Models and the event writer. No allocation change yet. Grocery tests still pass.
3. Medicine receipt validation and `UNRELEASED` on GRN and batch import. Adjustment layers for medicines use the new columns and do not overload `batch_number`.
4. `strict_order` inside `_consume`, gated on lot-controlled products. Grocery `fefo_order` untouched.
5. Transfer destination layers for medicines only.
6. Return quarantine for medicines only.
7. Recall tables, match, and the affected-sales query.
8. API routes for release, quarantine, and recall. UI on the stock-batch screens.
9. PostgreSQL concurrency test and RLS test.
10. Register fail-closed behavior, only after the offline decision in section 14. No `ProductOut` change unless that decision approves one boolean.
11. Full regression of the seven profiles plus pharmacy, then stop for acceptance. Prescriptions, dispensing, controlled registers, and insurance stay out.

## Files likely to be modified in 3B

- `apps/api/app/models/batch.py` — new nullable columns.
- `apps/api/app/services/batch_ledger.py` — one branch at the start of `_consume`. `fefo_order` and `_flag_expired_sale` stay.
- `apps/api/app/services/cost_layers.py` — medicine receipt and adjustment fields. Non-medicine `batch_number` behavior stays.
- `apps/api/app/services/inventory.py` — GRN line fields, transfer receive layer, medicine checks on manual add.
- `apps/api/app/services/import_batch_service.py` — map a manufacturer-lot column when the product is a medicine.
- `apps/api/app/services/returns_service.py` — quarantine after restore for medicines.
- `apps/api/app/services/expiry_service.py` — write-off of a medicine still goes through `move_stock`. No grocery change.
- `apps/api/app/schemas/batches.py` and the GRN receive schema — input fields.
- `apps/api/app/routers/v1/pharmacy.py` — lot and recall routes.
- Business Pro batch and recall screens. Not the product master lot fields.
- Register checkout, only after the offline decision.

Not modified for grocery behavior, and not modified in 3A: `fefo_order`, sale age limit, `ProductOut`, SQLite schema, capability presets of the seven profiles.

## New files proposed

- `apps/api/alembic/versions/20261118_0115_pharmacy_lots.py`
- `apps/api/app/models/pharmacy_lots.py` — events, recalls, recall lots. Status constants can live here.
- `apps/api/app/services/pharmacy_lots.py` — eligibility, `strict_order`, release, quarantine, recall match.
- `apps/api/app/schemas/pharmacy_lots.py`
- `apps/api/tests/test_pharmacy_lots.py`
- A PostgreSQL-only concurrency and RLS test module.

## Services to reuse

- `inventory.move_stock`, `reserve`, `release`, `receive_purchase_order`, `ship_transfer`, `receive_transfer`, `manual_adjust`.
- `batch_ledger._draw`, `on_movement`, `link_sale`, `restore_sale_item`.
- `cost_layers.record_receipt_layer` and `record_adjustment_layer`.
- `sale_service.record_sale` and the sync caller that commits it.
- `returns_service` document, tenders, and `restore_sale_item`.
- `payables_service` for the supplier bill. It does not move stock.
- `expiry_service.write_off` for expired units after they have been blocked from sale.
- `audit.record` and the new `batch_item_events` together. The event is the lot history. `audit_logs` remains the user-action log.

## Risks

| Risk | Why it matters | Mitigation in this design |
|---|---|---|
| Editing `fefo_order` "just for pharmacy" | Pharmacy and grocery share `Capability.FEFO` | Branch on the product, before `fefo_order` |
| Treating `batch_number` as the lot | Breaks tenant uniqueness and rewrites grocery document numbers | New nullable column. No backfill |
| Destination transfer without a layer | Medicine arrives and cannot be sold, or is sold from unlayered stock | Fail closed, and open an `UNRELEASED` destination layer |
| Offline sale from `stock_quantity` | Sells recalled or expired packs | Do not queue the sale when the server cannot validate |
| `sale_items.batch_item_id` used as the only trace | Misses the second lot of a split | Recall query reads `batch_allocations` |
| Release implemented as a manager PIN | Looks like a pharmacist check and is not one | No release endpoint until section 14 is decided |
| Alembic downgrade used in production | Drops columns under live rows | Redeploy the previous app. Leave the columns |
| Double quantity on transfer receive | On-hand already increased by `TRANSFER_IN` | The new layer records the same units. It does not call `move_stock` again |
| Existing pharmacy stock becomes unsellable | Null status is ineligible | Intended. A person enters the real lot and releases. No fabricated lots |

## Acceptance criteria for Stage 3B

Stage 3A itself is complete when this document exists and no application or database file has changed.

Stage 3B, later, is accepted only when:

- Medicine lots are `batch_items` rows, with quantity still equal to `quantity_remaining`.
- Grocery `fefo_order` and `EXPIRED_STOCK_SOLD` tests pass unchanged.
- The other six profiles pass their inventory and sale tests.
- A medicine cannot be sold when the only stock is expired, quarantined, recalled, unreleased, or missing an expiry.
- A sale that spans two lots stores both allocations in the same transaction as the sale.
- A shortfall rolls back the sale.
- A recall lists every sale that consumed the lot, including split lines.
- A transfer does not lose the manufacturer lot and does not double the quantity.
- Offline behavior matches the decision in section 14, and until that decision the register does not complete a lot-controlled sale it cannot validate.
- Disposable PostgreSQL can migrate `0114` → `0115` → `0114` without changing existing quantities.
- Prescriptions, dispensing, controlled registers, insurance, and regulator notifications are still absent.

## Stage 3A completion

The inventory call paths above were traced through `move_stock`, `batch_ledger`, receiving, transfers, adjustments, expiry write-off, returns, reservations, payables, and the register cache.

No application source, migration, schema, seed, quantity, grocery rule, sale posting, or POS code was changed. Implementation waits for explicit approval of Stage 3B.
