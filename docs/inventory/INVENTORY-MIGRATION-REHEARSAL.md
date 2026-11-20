# Inventory migration and restore rehearsal

Date: 20 November 2026. The acceptance database and the developer database were not migrated.

## Baseline

The operational head is `20261119_0120`. Its `down_revision` in `apps/api/alembic/versions/20261119_0120_user_preferences.py` is `20261119_0119`. That is the supported previous revision. It was not chosen as a guess.

## Upgrade

A disposable Postgres 16 container on `127.0.0.1:55455` received an empty database, `inventory_from_0119`.

1. Alembic upgraded that database to `20261119_0119`.
2. Two tenants were inserted. PRIOR-A had on-hand 7 and one purchase movement. PRIOR-B had on-hand 4 and one purchase movement.
3. Alembic upgraded to head. A second upgrade applied nothing and stayed at `20261119_0120`.
4. Both quantities, tenant ids, and movement ids were unchanged.

`ai_pos_app` was created on that database as `LOGIN`, `NOSUPERUSER`, `NOBYPASSRLS`. The session user was `ai_pos_app`, not a superuser using `SET ROLE`. With tenant A set, PRIOR-A was visible and PRIOR-B was not. An empty tenant setting returned 0 products. A cross-tenant insert returned SQLSTATE `42501`.

## Backup and restore

`pg_dump -Fc` of `axizpos_inventory_acceptance` was 1,008,693 bytes, SHA-256 `fbc52e626a5bbaec8a56b537eb4c47309451fb7a4bfad4863d45aa4e63e5e894`. `pg_restore` into a second disposable database exited 0. Product, movement, purchase-order, and transfer counts matched the source. The restored oats on-hand quantity was 2.

The dump file and the disposable container were removed. The acceptance database was only read.

Evidence: `acceptance/inventory/evidence/final-release/migration-rehearsal.json`.

## Rollback

Do not downgrade a database that already has sales. The release rollback is to redeploy the previous application and leave `20261119_0120` in place. `20261119_0120` adds `user_preferences` and does not rewrite stock quantities.

## Status

Migration rehearsal: **PASSED**. Backup and restore: **PASSED**.
