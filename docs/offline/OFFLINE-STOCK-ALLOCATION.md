# Per-terminal stock allocation

Phase O4 design. Status: **IN PROGRESS**. Decision B is the policy. No allocation table exists yet.

Date: 22 November 2026. No database was changed. The developer database and the inventory acceptance database were not opened.

## Ledger rule

Branch truth stays `inventory_levels` and `stock_movements`. Services keep using `move_stock`. `quantity_on_hand` and `quantity_reserved` stay non-negative. Movements stay append-only and non-zero.

An allocation is a reservation of existing available stock for one device. It is not a second on-hand number.

`batch_allocations` stays the record of which purchase lot a posted movement drew. The new terminal allocation is a different record. The two meet when a consumption event posts: the movement is written once, and the batch draw hangs off that movement as it does today.

## Server record

One allocation identifies:

- Allocation id.
- Tenant, branch (`store_id`), terminal (`devices.id`), device identity.
- Product.
- Batch or lot when the product is lot-tracked.
- Serial or IMEI when the unit is serialized.
- Allocated quantity, consumed quantity, and remaining quantity.
- Unit and the integer precision already used for that product (pieces, or grams for weighed items).
- Allocation version.
- Created time.
- Status: `ACTIVE`, `EXHAUSTED`, `RELEASE_PENDING`, `RELEASED`, `RECONCILIATION_REQUIRED`.

Remaining quantity is allocated minus consumed. Both are integers in the product's base unit. A check constraint keeps consumed within allocated and remaining at or above zero.

Creating an allocation increases `inventory_levels.quantity_reserved` by the allocated quantity, inside the same database transaction as the allocation row, and only up to `quantity_on_hand - quantity_reserved`. The sum of outstanding allocations for a product at a branch cannot exceed available stock.

Example the acceptance test must use: branch available 100. Terminal A 40, B 35, C 25. A further allocation is refused. Overlapping serials are refused. The same lot quantity is not given to two terminals.

Release decreases `quantity_reserved` by the unconsumed remainder and sets the allocation `RELEASED`. Reallocation is an online workflow: release unused quantity, then allocate it to another device. A disconnected till cannot take another till's remainder.

## Register record

The SQLite allocation row stores the same identity, version, allocated, consumed, and remaining quantities. Checkout displays:

- Cached branch snapshot (informational).
- Allocated quantity.
- Consumed quantity.
- Remaining offline allocation.
- Quantity in the outbox that is not yet acknowledged.

The branch snapshot is not shown as the quantity this till can sell.

## Consumption

An offline sale of a tracked item posts in one SQLite transaction:

- Local sale, lines, and tenders.
- Decrement of remaining allocation, refused when the line quantity exceeds remaining.
- The outbox event, including allocation id, allocation version, event id, device sequence, user, branch, terminal, product, quantity, and timestamp.

Any failure rolls the transaction back. The local remaining quantity cannot go negative. A manager override does not insert stock. An edit of a local number is not an allocation.

When remaining is zero the till still checks out other lines it can cover. The short line shows the exact shortage. Replenishment is a request sent after connectivity returns. The till does not borrow.

## Reconciliation

On connect, consumption events push through the existing sync path:

1. Server checks device, terminal, tenant, branch, and allocation version.
2. Server checks each event id and quantity against remaining allocation.
3. Accepted events call `move_stock` once. The idempotency row on `sync_events` makes a replay a duplicate with no second movement.
4. The server acknowledges the event. The register stores that acknowledgement.
5. Consumed quantity on the server allocation increases by the accepted amount. `quantity_reserved` falls by the same amount because the units have left on-hand. Remaining allocation is allocated minus consumed.
6. Unused quantity can be released or renewed by an authorized online action.

A version or quantity conflict keeps the local sale, marks it `RECONCILIATION_REQUIRED`, and surfaces it to a manager. The server does not delete the event and does not overwrite on-hand to match the till.

## Returns

An offline return must point at a cached sale and pass the current return checks: the sale exists, the item was sold, returnable quantity remains, this return was not already posted, the role may refund, and the profile rules allow it.

The returned quantity is recorded as pending reconciliation. It does not increase remaining allocation. The server posts `RETURN_IN` only after it accepts the event. A repeated offline return of the same units is refused locally by the returnable-quantity check and refused again on the server by the existing return path.

## Special classes

| Class | Rule |
| --- | --- |
| Serial / IMEI | The allocation names the serial ids. The server will not assign one serial to two devices. Offline sale of an unallocated serial is refused. |
| Batch and expiry | Only lots that current release, recall, and quarantine rules allow are allocatable. Expired, recalled, and quarantined lots stay out of the allocation. |
| Weighed items | Quantity stays the integer base unit. Rounding cannot exceed remaining allocation. |
| Restaurant ingredients | A recipe deduction consumes an ingredient allocation or a recipe budget assigned to that terminal. There is no unbounded offline ingredient draw. |
| Laundry consumables | Detergent, chemicals, labels, and packaging use this allocation when the offline operation consumes them. Garments in cleaning are not stock products. |
| Pharmacy | Offline medicine sales stay blocked by `blockPharmacyOfflineSale`. Lot rows in the cache do not authorize a sale. Recall and pharmacist rules need a separate safety design before any offline medicine sale is considered. |

Store-local network coordination between tills is out of the first release. Each till trusts only its own allocation.

## Tests O4 must record

Two or more independent register databases, one disposable PostgreSQL database, initial stock 100, allocations 40 / 35 / 25, all disconnected. A sells 15, B sells 10, C sells 25. A cannot sell 26, B cannot sell 26, C cannot sell 1. Reconnect in different orders. Consumed total is 50, remaining branch stock is 50, movement count matches the sales, on-hand never goes negative, and each allocation still belongs to its device.

Repeat the shape for weighed goods, serials, batch and expiry, recipe ingredients, and laundry consumables. Pharmacy asserts the offline medicine block still fires.

O1 did not run these tests.
