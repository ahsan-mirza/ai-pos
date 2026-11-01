# AxizReach API

All portal routes stay under `/api/v1/reach` and require `messaging.manage` plus the `axiz_reach` capability. The tenant comes from the request, not the body.

| Method | Path | Purpose |
|---|---|---|
| GET, PUT | `/channels` | Channel on/off and provider. Secrets are masked. |
| POST | `/channels/{channel}/test` | Marks a configured channel connected. |
| GET | `/overview` | Counts, delivery rate, credits, connection, recent campaigns. |
| PUT | `/prices` | Per-channel usage cents. Does not move the credit ledger. |
| GET | `/customers?q=` | Customer master search, including marketing opt-in. |
| POST | `/campaigns/preview` | Eligible, suppressed, estimated cents and credits. |
| GET, POST | `/campaigns` | List and launch. Launch is idempotent on `idempotency_key`. |
| GET | `/campaigns/{id}` | One campaign in this tenant. |
| POST | `/campaigns/{id}/pause`, `/resume`, `/cancel` | Pause holds queued rows. Cancel skips them and releases credits. |
| GET | `/messages` | Recipient history. Optional `campaign_id` and `status`. |
| GET, PUT, DELETE | `/templates` | Saved message bodies for the current content payload. |
| GET, POST | `/connections` | Evolution sessions for this tenant. |
| POST | `/connections/{id}/connect`, `/status`, `/disconnect` | QR, refresh, logout. |
| GET | `/credits`, `/credits/transactions` | Prepaid balance. Missing account returns zeros. |
| POST | `/webhooks/evolution/{webhook_key}` | Evolution callback. Header `apikey` must match `EVOLUTION_WEBHOOK_SECRET`. |
| POST | `/api/v1/super-admin/tenants/{id}/reach/credits` | Console admin allocation. Idempotent. Writes an operator audit row. |

Webhook payloads are matched to `reach_connections.webhook_key`. A tenant id in the body is ignored. With tenancy on, the API scans active tenant databases. With tenancy off, it uses the request database.
