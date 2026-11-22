# O5 conflict classification

Classification follows the existing `push_batch` rules. O5 does not add a new validator and does not reject a queued sale because the catalogue price later changed.

| Situation | Server result | Local status | Automatic retry |
| --- | --- | --- | --- |
| Same idempotency key, same canonical payload, already applied | 200 `duplicate` | `synced` | No |
| Same key, different payload | 409 `idempotency_conflict` | `conflict` | No |
| Repeated key inside one request | 422 `duplicate_idempotency_key` | `rejected` | No |
| Domain `SyncRejected` (unknown product, inactive product, stock shortfall, return quantity, missing sale) | 422 `sync_rejected` | `rejected` | No |
| Batch larger than `sync_max_batch_size` | 413 `batch_too_large` | `rejected` | No |
| Unique-key race, same hash already stored | 200 `duplicate` via `_duplicates_after_rollback` | `synced` on the retry that receives it | The in-flight request is not applied twice |
| Unique-key race, hash differs | 409 `idempotency_conflict` | `conflict` | No |
| Auth failure, network loss, 5xx | No committed outcome is known to the register | `pending` | Yes, original key and payload |
| Catalogue price or tax changes after the sale was queued | Not a server conflict. The queued payload is the snapshot | `pending` until a normal push | The original snapshot is what is pushed |

Stock shortfalls stay 422. They are not solved by changing `inventory_levels`, reallocating a terminal, or inserting a compensating movement.

A return that fails validation stays `rejected` with its original payload. It is not deleted and it is not turned into a second return.

Tenant, branch, and device checks stay in the existing middleware and `require_device`. O5 does not add a path around them.

Financial adjustment of a conflicted amount is not classified as auto-resolvable. See `O5-RECONCILIATION-RULES.md`.
