# AxizReach deployment

The plugin is imported by the existing API. No extra Compose service is required.

Set these on the API process when a store will use Evolution:

- `EVOLUTION_API_URL` — base URL of the central Evolution API
- `EVOLUTION_API_KEY` — server key sent as the `apikey` header
- `EVOLUTION_WEBHOOK_SECRET` — shared secret Evolution must send as `apikey` on callbacks

Point Evolution webhooks at `/api/v1/reach/webhooks/evolution/{webhook_key}`. The key is created with the connection and is not shown in the portal API.

Apply tenant migrations with the existing Alembic command. Revision `20261101_0095` lives in `plugins/reach/backend/migrations` and revises `20261031_0094`. `apps/api/alembic/env.py` scans that directory and `apps/api/alembic/versions` on one version table. Do not move `20261030_0089` or `20261030_0090`.

Credits are allocated per store from the console: `POST /api/v1/super-admin/tenants/{tenant_id}/reach/credits`. Until that account exists, Evolution campaigns are refused and other providers keep working.

Redis and `dispatch_messages` stay as they are. Scheduled campaigns use `outbound_messages.next_attempt_at`.
