# O6 per-terminal allocation design

An allocation is a reservation for one device at one branch. It is not a second on-hand number.

## Record

`TerminalAllocation` stores the allocation id, manifest id, version, tenant, branch (`store_id`), terminal (`device_id`), device thumbprint, product, optional serial, optional lot (`batch_item_id`), unit (`each` or `g`), allocated quantity, consumed quantity, last sequence, status, policy version, signing key id, and the signed payload.

Statuses in use: `ACTIVE`, `EXHAUSTED`, `RELEASED`, `QUARANTINED`. A separate `RELEASE_PENDING` state is not stored. Confirmation and release are one authorized request.

`remaining = quantity_allocated - quantity_consumed`. Both quantities are integers. Grams are integers. There is no floating-point stock quantity.

## Issuance

`POST /api/v1/inventory/allocations` requires `inventory:adjust_stock`. A cashier token is refused.

The service locks the inventory row, checks `available`, then calls `inventory.reserve`. Two issuers cannot both reserve the same units: the second request sees the updated reserved quantity. A request that does not fit is rejected and writes no allocation.

A serial can sit on only one holding allocation. A lot cannot be allocated past `quantity_remaining` minus other holding allocations of that lot. A terminal is allocated only at its own branch, and only after it has a device thumbprint.

## Local balance

The register stores the signed manifest and a consumed counter in SQLite `terminal_allocations`. Checkout that carries `allocation_remaining` sells against that number, not `stock_quantity`. A missing allocation does not fall back to the branch quantity.

## Consumption

An allocated sale names `allocation_id`, `sequence`, `product_id`, and `quantity`. The server checks device, branch, thumbprint, status, product, and that the sequence is the next one. It releases that many reserved units and records a consumption row tied to the sale idempotency key. `record_sale` then calls `move_stock`. Both sit in the existing sync transaction.

A return posts `RETURN_IN` and does not increase the terminal's remaining allocation.
