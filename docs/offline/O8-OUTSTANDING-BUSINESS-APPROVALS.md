# O8.2 outstanding business approvals

Posting stays **AWAITING APPROVAL**. O8.11 settled disposable takeaway #3E55 as an ordinary cash sale, invoice `O810-DTA-000001`, on the SQLite acceptance API. That sale is not a lost-terminal stock write-off and not a financial conflict posting. The production public key stays **AWAITING APPROVAL**. The O8.10 Restaurant window opened takeaway Order #3E55 and did not charge it, write off stock, or post a financial adjustment. The production public key stays **AWAITING APPROVAL**. The O8.9 Restaurant provisioning run did not write off stock or post a financial adjustment. The production public key stays **AWAITING APPROVAL**. The O8.8 order-authorization run did not write off stock or post a financial adjustment. The production public key stays **AWAITING APPROVAL**. The request and decision records exist. No stock was written off. No conflict was adjusted. An approved row keeps `posting_status` at `awaiting_approval`. The submitter cannot decide the same request.

## Lost-terminal stock write-off

A terminal that never reconnects still holds `quantity_reserved` for its grants. Other terminals cannot sell that quantity. Branch on-hand is not reduced by the grant itself. The sale path releases the reservation and posts `SALE_OUT` only when that terminal's sale syncs.

Business impact: the reserved units stay unsellable until the terminal returns or an authorized person releases them. A silent write-off would hide stock that may still be in the shop, or would drop stock that was already sold offline and not yet synced.

Data and inventory risk: releasing the reservation without a confirmed sequence can double-sell. Writing the units off without a sale can understate stock if the terminal later syncs a sale. Quarantine already keeps the reservation when the terminal's sequence does not match.

Required authorization: a named inventory owner, the tenant, the branch, the terminal id, and the grant id. The action needs `inventory:adjust_stock` and a reason. It must not be available to a cashier on the missing terminal.

Audit: who approved it, when, the grant id, the quantity, the last confirmed sequence, and the remaining quantity. The existing stock movement is the ledger entry. A second ledger must not be added.

Reversal: if the terminal later syncs, the write-off has to be distinguishable from a sale so the delayed sale is not applied twice and is not dropped without a conflict record.

Recommended workflow: keep the reservation. Show the terminal as disconnected. Require a manager to confirm the last sequence and remaining quantity. Only then release or write off through the existing inventory adjustment, with the audit row. Do not do this automatically.

## Financial conflict adjustment

O5 quarantines a reused idempotency key whose payload hash differs. The original event stays. There is no Force Sync and no Ignore Conflict.

Business impact: the tender, tax, and stock on the two payloads can disagree. Auto-picking one of them can record money that was not taken, or drop a sale that was taken.

Data risk: changing the stored sale after a `409` would break the idempotency rule. A later retry of the original payload must still match the first hash.

Required authorization: a manager who can see both payloads, the key, the terminal, and the amounts. The decision is an explicit adjustment document, not a retry of the rejected event.

Audit: both payload hashes, the chosen outcome, the person, and the reason. The original queue row stays `conflict`.

Reversal: an adjustment needs its own document so it can be reversed without rewriting the quarantined event.

Recommended workflow: leave the conflict quarantined. A later, separately authorized adjustment creates a new event with a new idempotency key. It does not replay the rejected payload and it does not mark the conflict ignored.
