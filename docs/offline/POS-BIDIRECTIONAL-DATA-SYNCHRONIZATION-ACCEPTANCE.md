# POS bidirectional data synchronization

Date: 25-11-2026

Software status: **PASSED WITH LIMITATIONS**. Native acceptance: **NOT RUN**. This is not a new sync service. Sale, return, and allocation uploads stay on `sync_queue`. Catalogue, customer, and staff downloads stay on their existing cursors.

## Directions

POS to server for a new expense:

1. The row is stored in `local_expenses` with its original payload and idempotency key before the cashier is told it was saved.
2. Petty cash is reserved only when this register has a downloaded balance that covers the amount. Otherwise the row is Pending Review and is not described as a ledger posting.
3. `flush_local_expenses` posts that payload to `/api/v1/expenses` when the activated server can be probed.
4. The same `client_key` returns the original expense. A retry does not post a second petty-cash movement.
5. The local row becomes Synced only after that response. A network failure leaves it pending.

Server to POS:

The expenses list is still `GET /api/v1/expenses` when the register is online. Pending local rows are shown with that list. There is no second download cursor for expenses. Product, customer, and staff downloads were not changed.

## Conflicts

A repeated expense key keeps the first server row, including its original description. Sale and stock conflicts stay on the O5/O6 rules. Settings, tax, and security records are not last-write-wins in this pass, and they are not newly queued offline.

## Tests

Rust `local_expenses`: a repeated key does not reserve petty cash twice, and a missing balance stays Pending Review.

The API test `test_offline_client_key_posts_once` is in `apps/api/tests/test_expenses.py`. It was not executed here because the API test environment failed to import `phonenumbers`.

## Native acceptance

Not run. No disposable register was taken offline, used to create an order and an expense, restarted, and then reconnected so Business Pro could be checked.

## Limitations

- Top-up, float count, void, and supplier creation stay online.
- VAT on a pending expense is not the server's figure. The server calculates it on accept.
- A pending expense is excluded from the recoverable-VAT card.
- Identity and security settings are not queued.
- Upload and download cursors for sales were not merged, and they were not redesigned.
