# Deployment

Production in this repository is PM2 plus nginx. The plugin is not registered in `deploy/ecosystem.config.cjs`, so a normal deploy does not start it.

Prepared files, unused until an operator approves them:

- `deployment/ecosystem.einvoicing.cjs` — `axizpos-einvoicing-api` on `127.0.0.1:8090` and `axizpos-einvoicing-worker`.
- `Dockerfile` — local image only. Production does not require Docker.
- `.env.example` — `DATABASE_URL`, `JWT_SECRET`, `EINVOICING_CREDENTIAL_KEY`.

The portal currently talks to the API, and the API imports the plugin, so the portal works without the standalone process. The worker is still required to drain `einvoicing_outbox`. Until the worker runs, rows stay `PENDING` and invoices are not submitted.

## Migration

From `plugins/einvoicing`, with `PYTHONPATH` set to that directory and `DATABASE_URL` pointing at a disposable copy:

```
alembic upgrade head
alembic downgrade base
```

`downgrade` drops only the ten plugin tables. Do not point `DATABASE_URL` at the live `ai_pos` database for this step. The revision has not been applied.

## Routing

If the standalone API is started, nginx can proxy `/einvoicing-plugin/` to `127.0.0.1:8090` with the same TLS certificate as the API server. The portal does not need that location while it uses `/api/v1/einvoicing` on the main API.

## Health

`GET /health` and `GET /ready` on port 8090. The worker has no HTTP port; a stuck `PENDING` row older than the retry window is the operational signal. Logs use the process stdout, which PM2 already captures for the other apps.

## Rollback

Stop the two PM2 apps, leave the tables in place (they are unused when the capability is off), and downgrade the plugin revision only on a database that has no e-invoice rows you must keep. Core sales, VAT, and subscriptions are not in the downgrade.
