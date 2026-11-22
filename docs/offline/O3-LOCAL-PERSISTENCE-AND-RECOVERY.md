# Local persistence and recovery

The register SQLite file gains two tables. `sync_queue` is unchanged.

`bootstrap_state` holds one row: generation, status, last applied sequence, and the opaque cursor. `bootstrap_stage` holds rows for a generation that is not yet the catalogue checkout reads.

`Db::stage_products` writes the staging rows. A repeated page with the same payload is ignored. A repeated page with a different payload fails and rolls back. Checkout still reads `products`.

`Db::activate_bootstrap` copies the staged rows into `products` only when the staged count matches the expected count. The delete and insert run in one transaction, together with the status and cursor. A short download returns an error. If an earlier generation was already activated, the status returns to `complete` and those products stay. The queue is not in the statement.

`Db::apply_product_pull` checks that new sequences are contiguous, applies them, and stores the next sequence and cursor in the same transaction. A gap or a bad payload rolls the batch back. The cursor does not move.

The readiness command treats a missing `bootstrap_state` row as `incomplete`, so a product cache from the older full refresh is not `OFFLINE_READY`. The library helper still treats an empty status as the O2 path when a caller passes that explicitly. A row in `in_progress` or `failed` is reported as that state and does not by itself delete the previous products.

These cases are covered by `bootstrap::tests` in the desktop crate: a one-row shortfall, a queued sale left in place, a duplicate page, a duplicate pull, a gap, and a tombstone that keeps the product row.
