# O6 reservation, release, and recovery

## What holds stock

While a grant is `ACTIVE` or `QUARANTINED`, its unconsumed quantity stays in `quantity_reserved`. Other sales, adjustments, and new allocations see that quantity as unavailable. Going offline does not release it. There is no time-based expiry.

## Release

`POST /api/v1/inventory/allocations/{id}/release` requires `inventory:adjust_stock` and a confirmed sequence and remaining quantity that match the server. The unused remainder is passed to `inventory.release`. The status becomes `RELEASED`. The old manifest cannot be consumed. The released units can be allocated again.

A mismatch is HTTP 409 `sequence_mismatch`. Nothing is released.

## Lost terminal

`POST /api/v1/inventory/allocations/{id}/quarantine` sets `QUARANTINED` and leaves the reservation in place. Another terminal cannot take those units. Quarantine does not free stock and does not write a stock movement.

Writing the reserved units off because a device is destroyed is not implemented. That decision is **AWAITING APPROVAL**. A disconnected terminal cannot learn about a later physical loss until it syncs.

## Replenishment

A further grant is a new allocation, issued online, for quantity that is still available. The register cannot raise its own balance.

## Returns

`RETURN_IN` increases on-hand only. It does not increase `quantity_consumed` backwards and does not add to the terminal's remaining grant.

## Local recovery

If the signed manifest fails verification, it is not installed. If a local consume does not fit, the sale queue row is not written. Restoring an older SQLite file is not prevented by DPAPI. DPAPI protects `terminal.bin`, not a copied database. A restored allocation file could under-count consumption until the next sync. The server still refuses a sequence that does not follow `last_sequence`, so a replay does not post a second movement. This anti-rollback gap is a limitation.
