# Inventory security and data integrity

Date: 19 November 2026. This is a review of the paths exercised on the disposable inventory acceptance stack and of the authorization code those paths use. It is not a completed penetration test.

## What was verified

| Control | Evidence |
|---|---|
| Tenant scope | Grocery `inv-accept` product list returns oats, rice, and `INV-TIN`. The medicine row belongs to a different tenant id and is not in that list. |
| Branch scope | The oats level exists only on Acceptance Store A. |
| Server-side uniqueness | Duplicate SKU and duplicate barcode return HTTP 409. No extra product or movement was created. |
| Catalog writes | Categories, brands, and models use `require_catalog_admin`. A store-bound Floor Manager receives 403. The register now hides those write controls when `store_id` is set. The API remains the enforcement. |
| Device versus user | `GET /api/v1/products` allows a device principal. `GET /api/v1/inventory/stock` does not. An enrolled device receives 403 `This action requires a signed-in user.` |
| Cashier | PIN login succeeds with the enrolled terminal token. Stock then returns 403 `You do not have permission for this action.` Password login for the cashier is 403 because that account has no portal access. |
| Stock writes | Opening stock for oats is one `opening_balance` movement. The cancelled purchase orders did not add movements. No SQL quantity update was run. |
| Images | Oats photos are WebP files under `apps/api/storage/inv-accept/media/`. The image service rejects other types and files over 5 MB, then re-encodes. |
| Acceptance isolation | Diagnostics record `developer_env_loaded: false` and API `http://127.0.0.1:18081`. The identifier is `com.axizpos.inventory.acceptance`. |
| Device credential | The device row is not revoked. The stale copy in the acceptance runtime file returned 401. The sealed terminal token for this acceptance identity is valid. The runtime file was updated to that enrolled token. No developer key and no installed-register key was copied. |

Application-role RLS (`ai_pos_app`, `NOBYPASSRLS`) was verified in the pharmacy Stage 3F.2 disposable database. That database has been removed. This stage did not open a new RLS session as `ai_pos_app`. Queries used the acceptance database owner, which bypasses RLS, so they are not RLS evidence.

## Not claimed

Upload of a hostile file, price tampering, cross-tenant image fetch, and a revoked-device retry were not executed in this pass. Logs were not audited for a request id on every error.

## Status

Security and data integrity: **PASSED WITH LIMITATIONS**.
