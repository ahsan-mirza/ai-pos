# O5 reconciliation rules

No existing workflow was found that may rewrite a committed sale, invent a provider `PAID` result, or adjust stock to absorb an offline conflict. O5 does not add one.

## What the register may do

| Conflict | Permitted action | Authority |
| --- | --- | --- |
| `pending` after a network or server-unavailable error | Automatic flush retries the original payload and key | Existing sync engine |
| `conflict` (same key, different payload) | Keep the row. Show it in the status chip. Do not resubmit it automatically | No cashier override |
| `rejected` (validation, stock, return quantity, batch size) | Keep the row. Do not resubmit it automatically | No cashier override |
| `synced` after `applied` or `duplicate` | Stop sending that batch | None further |

There is no Force Sync control and no Ignore Conflict control.

## What stays unresolved

Changing the money, tax, or stock on an original sale or return to clear a conflict requires an authorized business workflow that this phase did not find. Those events stay `conflict` or `rejected` with the original payload.

Status of a financial or stock adjustment: **AWAITING APPROVAL**.

Rules that hold without that approval:

1. The original payload in `sync_queue` is not rewritten to a new total.
2. The idempotency key is not replaced.
3. The queue row is not deleted.
4. No provider payment result is created.
5. A sale is not marked paid by the conflict path.
6. `_apply_event` does not dispatch a duplicate.
7. Tenant and device authentication stay on `push_sync`.
8. The status chip does not grant a cashier a resolve action.
9. A return is not fabricated from a conflict.
10. `last_error` records the server message. The payload remains the audit of what was queued.

A corrective sale or return, if the business later approves one, must be a new event through the existing sale or return workflow, with its own idempotency key. O5 does not create that event.
