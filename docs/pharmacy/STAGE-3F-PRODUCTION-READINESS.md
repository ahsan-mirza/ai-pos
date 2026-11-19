# Stage 3F — Production readiness

This is a prerequisite list. It is not a deployment, and pharmacy is not activated for any production tenant.

## Migration heads inspected

| Plane | Apparent head | Parent |
|---|---|---|
| Operational | `20261119_0120` user preferences | `20261119_0119` |
| Control | `control_0041` pharmacy demo | `control_0040` |

Pharmacy operational chain: `20261118_0114` catalogue, `0115` lots, `0116` lifecycle, `0117` pharmacist authorization, `0118` governance, `0119` application-role RLS, then `0120`.

`20261119_0119` rewrites policies on `batch_items`, `batch_item_events`, `pharmacist_authorizations`, `pharmacy_governance_officers`, `pharmacy_recalls`, `pharmacy_recall_lots`, `pharmacy_supplier_returns`, and `pharmacy_supplier_return_lines` so `app.bypass_rls` does not widen visibility for the non-owner application role.

Stage 3F.1 upgraded an empty disposable database, `127.0.0.1:55442/stage3f1_alembic`, from no revision to `20261119_0120`. A second upgrade applied nothing. The release race downgraded to `20261118_0116` and the governance race to `20261118_0117`, then both returned to `20261119_0120`. The container was removed. Do not downgrade a production tenant. The Stage 3 architecture rollback is to redeploy the previous application and leave the columns in place.

## Database role

Stage 3E.6.1 disposable acceptance used `ai_pos_app` with `NOSUPERUSER` and `NOBYPASSRLS` against `127.0.0.1:55432/axizpos_pharmacy_acceptance`. That database was not the development database and not production. A production cutover must use an equivalent non-owner role. Catalog flags alone are not the proof. A session without `app.tenant_id` must fail closed, and a session for tenant A must not read or write tenant B. Re-run that probe on the target database before go-live.

## Capability

Pharmacy catalogue capability is per tenant. Do not enable it globally. A grocery, electronics, wholesale, fashion, restaurant, cafe, or quick-service tenant must not receive it as part of a pharmacy release.

## Secrets and logging

Production needs the existing API, database, and device-token secrets in the environment, not in the repository. Logs must not contain passwords, PINs, JWTs, device tokens, or activation codes. This stage did not add a new logger. A log review before go-live is still required.

Sale upload stays on the terminal device token. Cashier authorization stays separate. No defect was found that requires merging those two.

## Desktop

`apps/desktop` `tauri:build` and `build:win` call `scripts/require-pos-signing.mjs`. A production installer is refused unless `AXIZPOS_SIGN_THUMBPRINT` is a 40-character certificate thumbprint. The private key stays in the certificate store. Do not publish an unsigned installer. This stage did not build or sign one.

## Network and operations

Nginx, network restrictions, monitoring, backups, and restore were not changed and were not rehearsed in this stage. Before production:

- Confirm the reverse proxy does not expose the database.
- Confirm request ids already used by the API are retained for pharmacy routes.
- Take a backup of the operational and control databases and restore it onto a disposable server once.
- Confirm the application role used by the API matches the RLS role above.
- Keep a previous application build available. Do not use Alembic downgrade as the incident rollback.

## Not done

- No disposable migration rehearsal in this stage.
- No performance measurement.
- No production configuration edit.
- No tenant activation.
