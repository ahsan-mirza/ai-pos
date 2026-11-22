# O4 recovery and durability

SQLite is the register database opened by `Db::open`. `PRAGMA foreign_keys = ON` is set. Journal mode, WAL, and busy timeout were not changed. No defect in those settings was identified, and a second database was not added.

## What a failed step leaves behind

| Point | Result under test |
| --- | --- |
| Staged product count does not match | `activate_bootstrap` returns an error. Previous products, previous checkout settings, and `sync_queue` stay. Status returns to `complete` when an older generation was already active |
| Return payload fails the cashier or store check | `returns.rs` `enqueue` returns before the transaction. `pending_count` stays 0 and no `local_returns` row is written |
| Same sale idempotency key queued again | The second `enqueue` fails. One pending batch remains |
| Pull sequence skips a number | `apply_product_pull` returns "pull batch skipped a change". `last_seq` is unchanged |
| Process closes after a successful enqueue | Reopening the same file returns the same batch id, idempotency key, and payload amounts |

## Restart

`bootstrap.rs` `a_queued_sale_keeps_its_price_after_restart_and_a_later_catalogue_price` closes the database, opens it again, and reads the queued sale. The total, tax, and unit price match the inserted payload after a later product price was applied.

`checkout_settings_activate_with_the_catalogue_and_do_not_rewrite_a_queued_sale` applies a later currency and tax rate through a `settings` pull. The queued sale still has the original currency and tax. A short following generation does not replace the active currency.

`a_return_and_its_queue_row_commit_together` reopens the file and still finds the return event and its idempotency key.

## What was not injected

A full disk, a killed process mid-write, and a forced SQLite busy response were not simulated. The tests use temporary database files and the normal commit or rollback of a `rusqlite` transaction. Native window restart was not run.

## Replay

The server idempotency row is unchanged. Applying the same event key again is a duplicate in `sync_service.py` and does not post a second sale. The historical O3 run of `test_duplicate_event_does_not_apply_twice` passed; that test was included again in the O4 API run.
