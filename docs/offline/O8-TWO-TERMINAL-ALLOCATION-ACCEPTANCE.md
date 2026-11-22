# O8.2 two-terminal allocation acceptance

Status: **PASSED WITH LIMITATIONS**.

No new ledger was added. Grants still reserve `quantity_reserved`. Sale consumption still goes through the existing stock movement on sync. Branch on-hand is not used when `allocation_remaining` is present.

## What this run executed

API, included in the 28 tests that passed in 27.37s:

`test_allocations_cannot_exceed_or_overlap_branch_stock` starts from 100 on hand. It grants 40, 35, and 25 to three devices. A further grant of 1 returns `allocation_exceeds_stock`. On hand stays 100. Reserved becomes 100. The 25 is a third grant, not an unallocated remainder.

`test_offline_sales_consume_only_their_own_allocation` grants 40 and 35. Terminal B cannot push a sale against A's grant (`422`). A's sale consumes 30. A replay is `duplicate` and does not consume again. A changed payload on the same key is `idempotency_conflict`. An overspend stays `422` and consumed stays 30. Two `SALE_OUT` movements total -55.

Desktop library, included in the 53 tests:

`a_sale_and_its_allocation_commit_together_and_cannot_overdraw` sells inside a grant of 40, leaves 10, and an overdraw writes no queue row. The remainder is still 10 after that refusal.

`an_offline_sale_writes_the_grant_sequence_and_an_overdraw_writes_nothing` keeps the same remainder.

`a_tampered_or_foreign_manifest_is_rejected` omits a manifest that does not verify.

Vitest `allocation.test.ts`, 2 tests inside the 7 that passed:

The stamp sets `allocation_remaining` from the allocation map and leaves `stock_quantity` at 100. A product missing from the map is stamped null. An online product is not stamped.

## Not run

The product card, barcode lookup, search, variant selection, and cart were not clicked in a Tauri window. The native restart of a register was not run. Online sale refusal of a reserved quantity is covered by the API reservation tests in the same file, not by a second live register.

The requested split of 40, 35, and 25 unallocated was not the shape of the executed API test. The executed test reserved the last 25 as well.
