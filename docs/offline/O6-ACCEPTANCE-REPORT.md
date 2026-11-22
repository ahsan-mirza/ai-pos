# O6 acceptance report

Status: **PASSED WITH LIMITATIONS**.

Allocations reserve existing branch stock. `inventory_levels` and `stock_movements` remain the stock ledger. `sync_queue` was not replaced. No production deployment. No developer, inventory-acceptance, laundry, or production database was opened. Alembic `20261122_0127` was not applied to those databases.

## What was executed

- Branch stock 100. Grants of 40, 35, and 25. A further unit is refused. On-hand stays 100. Reserved becomes 100. No extra stock movement is written for the grant.
- Two terminals sell 30 and 25 against their own grants. Each other's grant is refused. Replay is `duplicate` with two `SALE_OUT` rows, not four. A changed payload on the same key is `idempotency_conflict`.
- A batch whose second event has a bad sequence returns 422. Consumed quantity stays 0 and no `SALE_OUT` is written.
- With 80 reserved, an online sale of 21 is refused and a sale of 20 posts. Reserved stays 80. A further removal through `move_stock` is refused.
- A return movement increases on-hand and leaves the terminal remainder unchanged. Release requires the synced sequence. After release, reserved returns to 0 and the old grant cannot be consumed.
- Quarantine keeps the reservation. Another terminal cannot take that reserved quantity.
- A cashier cannot create an allocation.
- 25.500 kg is 25500 grams. Selling 4.250 kg leaves 21.250 kg. 21.251 kg is refused.
- The same serial cannot be allocated to two terminals. The same lot cannot be over-allocated.
- Two writers each requesting 60 from 100: one allocation, reserved 60.
- The register rejects a tampered manifest and a manifest for another terminal. Local consume and the queue row commit together. An overdraw leaves both unchanged across restart.

## Commands and counts

`node scripts/python.mjs -m pytest tests/test_allocations.py tests/test_sync.py tests/test_permanent_entitlement.py -q --tb=line`

24 passed in 18.55s.

`cargo test --lib -- --test-threads=8` from `apps/desktop/src-tauri`

46 passed.

`pnpm exec vitest run src/features/checkout/allocation.test.ts src/features/checkout/checkout.pharmacy.test.ts` from `apps/desktop`

4 passed. The allocation case checks the offline message and does not use the branch quantity of 100. Pharmacy offline medicine checkout still fails closed.

These counts are this O6 run.

## Limitations

- Native Tauri window: **NOT RUN**.
- PostgreSQL RLS with `ai_pos_app`: **NOT RUN**.
- Cross-tenant HTTP: **NOT RUN**. Device and branch checks were executed on SQLite.
- Release builds still have no production entitlement public key. The test signing key is not a production key.
- Serial status changes can still pass `allow_reserved=True`. Quantity sales, adjustments, and transfer reservations use `available`.
- DPAPI does not stop restoration of an older register database. The server sequence check stops a second post. It does not stop a restored local balance from looking higher until sync.
- Destroying a lost terminal's reserved units is **AWAITING APPROVAL**. Quarantine does not free them.
- O5 still has no approved money or stock rewrite. O6 does not add one.
- Remote staff and permission changes still apply only after sync.
- O3 bootstrap tests were not part of this 24-test run.
- The cart blocks against `allocation_remaining` when that field is present. The live product card does not yet fill it from SQLite on its own. Local enforcement for a queued sale is `consume_allocation`, which was executed in the desktop library test.
- O7 and O8 were not started.

## Carry-forward

O1 remains PASSED. O2, O3, O4, and O5 remain PASSED WITH LIMITATIONS. The offline platform remains IN PROGRESS.
