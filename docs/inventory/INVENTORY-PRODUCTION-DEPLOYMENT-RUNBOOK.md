# Inventory production deployment runbook

Date: 19 November 2026. This runbook does not authorize a deployment. No production migration was run and no production tenant was activated.

## Blockers that must be cleared first

| Item | State |
|---|---|
| Code signing thumbprint `AXIZPOS_SIGN_THUMBPRINT` | Unset. `scripts/require-pos-signing.mjs` exits 1 until it is a 40-character certificate thumbprint. The private key stays in the Windows certificate store. |
| Production API base URL | Not recorded in this repository as a confirmed production value. Do not embed the acceptance URL `http://127.0.0.1:18081` or a developer URL. |
| Production database host, role, and backup location | Not inspected. Do not copy `.env`, `.env.inventory-acceptance`, or the acceptance runtime file. |
| Inventory Windows acceptance | Product create, gallery, and viewports on the acceptance register are not complete. |
| Business-profile acceptance | Only the grocery disposable tenant has current API checks. |

Until those are closed, deployment readiness stays blocked.

## Sequence to use after the blockers are cleared

1. Confirm the git revision, application version, and a signed installer whose signature verifies.
2. Take a production database backup and restore that backup onto a disposable server. Check that stock movements and invoice rows still balance. Do not treat an untested backup file as recoverable.
3. Run the application migrations on that disposable copy from the documented previous revision to the current Alembic head. The operational head in the repository is `20261119_0120`, parent `20261119_0119`. Confirm the control-plane head separately. Stop if the disposable upgrade fails.
4. Apply the same migrations to production only under a change window, with the backup verified and a person assigned to stop the rollout.
5. Install the signed register. Enrollment must use a new production device activation key. Do not reuse an acceptance or developer device token.
6. Smoke-test one store: sign in as a cashier and as an inventory manager, open stock, search a known product, and confirm a rejected unauthorized call. Do not create practice stock in production.
7. If the migration or the smoke test fails, restore the verified backup or move forward with a fix that has been rehearsed on the disposable copy. Do not invent a downgrade that the migration files do not support.

## Rollback

Alembic downgrade is only safe where the revision implements a downgrade and no later data depends on the new columns. Rehearse it on the disposable copy. If the downgrade is not implemented, recovery is the backup restore plus the previous signed installer.

## Health

The API process should answer its existing health route on the production host. The register diagnostics for a production build must show the production API host and must not show `developer_env_loaded` from an acceptance build. Acceptance builds refuse any API other than their dedicated loopback address.

## Status

The sequence above is the plan. It was not executed.
