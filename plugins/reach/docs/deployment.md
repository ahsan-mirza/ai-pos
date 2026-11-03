# AxizReach deployment

The plugin is imported by the existing API. No extra Compose service or Redis queue is required. `dispatch_messages` already runs inside the API process.

Production deploy copies `plugins/reach` next to `plugins/einvoicing`. The portal bundle includes the Reach page, and that bundle does not install this package. After deploy, `migrate-all` applies `20261101_0095` and `20261103_0096`.

Set these on the API process when a store will use Evolution:

- `EVOLUTION_API_URL` — base URL of the central Evolution API
- `EVOLUTION_API_KEY` — server key sent as the `apikey` header
- `EVOLUTION_WEBHOOK_SECRET` — shared secret Evolution must send as `apikey` on callbacks

When a connection is created, the API registers Evolution's webhook at `{PUBLIC_BASE_URL}/api/v1/reach/webhooks/evolution/{webhook_key}`. The key is not shown in the portal. Evolution must send `EVOLUTION_WEBHOOK_SECRET` as the `apikey` header. `REACH_SEND_INTERVAL_SECONDS` (default 3) spaces messages on one session, and `REACH_SEND_BATCH` (default 20) is how many of those messages one dispatch run sends.

Apply tenant migrations with the existing Alembic command. Revision `20261101_0095` lives in `plugins/reach/backend/migrations` and revises `20261031_0094`. `apps/api/alembic/env.py` scans that directory and `apps/api/alembic/versions` on one version table. Do not move `20261030_0089` or `20261030_0090`.

Credits are allocated per store from the console: `POST /api/v1/super-admin/tenants/{tenant_id}/reach/credits`. Until that account exists, Evolution campaigns are refused and other providers keep working.

Redis and `dispatch_messages` stay as they are. Scheduled campaigns use `outbound_messages.next_attempt_at`.
