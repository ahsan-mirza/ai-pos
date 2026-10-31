# Event contracts

## Outbox

`einvoicing_outbox` is the contract between the API and the worker.

| Field | Meaning |
|---|---|
| `kind` | `sale` or `return` |
| `source_id` | `sales.id` or `returns.id` |
| `status` | `PENDING`, then `DONE` or `DEAD` |
| `attempts` | Incremented by the worker. `DEAD` at 5. |

Unique `(tenant_id, kind, source_id)` makes a repeated sync a no-op.

The API writes the row in the same transaction as the sale, inside a savepoint. The worker commits after `process_outbox`.

## POS notice

The register does not emit a plugin event. After a successful or queued charge, if `uae_einvoicing` is enabled and the cart customer has `trn_vat_number`, the printed notice appends: the UAE e-invoice is pending and the receipt is not provider acceptance. The notice is taken before the cart is cleared.

## Webhook

See `ASP_INTEGRATION.md`. A stored event does not by itself mark an invoice accepted. Acceptance in the current code comes from `submit()`, which records the provider result on the invoice. A future ASP adapter can map a stored webhook onto a status transition; the mock does not.
