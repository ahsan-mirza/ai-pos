# API

Portal routes are mounted at `/api/v1/einvoicing` on the AxizPOS API. They use the existing bearer token and the bound tenant. A `tenant_id` field in a JSON body is removed before save.

| Method | Path | Gate |
|---|---|---|
| GET | `/dashboard` | `portal:reports_read`. Allowed without the add-on only when this tenant already has invoice rows. |
| GET | `/invoices` | Same. Query: `status`, `store_id`, `number`, `offset`, `limit` (capped at 100). |
| GET | `/invoices/{invoice_id}` | Same. Another tenant's id returns 404. |
| POST | `/invoices/{invoice_id}/retry` | Add-on required. 409 `not_retryable` when the status cannot move. |
| GET | `/configuration` | Add-on required. |
| PUT | `/configuration` | Add-on required. |
| POST | `/providers/test` | Add-on required. Body `provider_code`. Only `mock` succeeds. |

The standalone process repeats dashboard, invoice list, configuration, and provider test, and it adds:

`POST /api/v1/einvoicing/webhooks/{provider_code}`

Headers: `X-Einvoicing-Signature`, `X-Einvoicing-Timestamp`, `X-Einvoicing-Event-Id`, `X-Einvoicing-Participant`. This route does not use a portal JWT. It does not authorize from a body tenant id.

`GET /health` returns `{"status":"ok","service":"einvoicing"}`. `GET /ready` runs `SELECT 1` and returns 503 when the database is unreachable. The standalone process refuses authenticated routes when `JWT_SECRET` is unset.

Responses omit ciphertext. `invoice_public` returns the hash, internal status, provider status, and provider reference.
