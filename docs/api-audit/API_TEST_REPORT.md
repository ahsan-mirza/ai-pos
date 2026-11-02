# API test report

Date: 2026-11-02. Environment: local API against the development database for live HTTP checks, and the SQLite suite (`APP_ENV=test`) for pytest. No production traffic was sent.

## Inventory

`docs/api-audit/API_INVENTORY.md` lists **652** operations registered by `create_app()`. Nine are hidden from the OpenAPI schema. The auth column is inferred from endpoint parameter names: **546** look authenticated and **106** look public. Router-level permission and capability dependencies are not all visible on the function, so a "public" row can still require a signed-in user.

## Executed in this session

| Run | Result |
| --- | --- |
| `test_inventory.py`, `test_weighed.py`, `test_spec_scope.py`, `test_grocery.py`, `test_recipes.py`, `test_brands.py`, `test_price_includes_tax.py` | 28 passed |
| `test_unhandled_errors.py`, `test_inventory.py`, `test_tenancy.py` | 34 passed, then 1 new assertion failed because an unauthenticated create returns 401 before body validation. The assertion was corrected. |
| `test_unhandled_errors.py` after that correction | 10 passed |
| `test_variant_matrix.py`, `test_inventory.py` | 16 passed |

The suite on disk has **686** `test_` functions in **143** files. The runs above re-executed overlapping files. The other files were not executed in this session, so they have no new pass/fail from this audit.

## Live HTTP checks on the local tenant

Signed in as a portal user with `portal:inventory_manage`.

| Check | Result |
| --- | --- |
| `POST /api/v1/inventory/products` with price 15.00, opening stock 2, reorder 1 | 201 |
| `GET /api/v1/products/{id}` for that product | 200 |
| Eight further creates of the same shape | all 201 |
| `POST` with `price_cents` 3000000000 | 422, field error on the selling price |
| `GET /api/v1/products?limit=50` | 200, 2 rows |
| `GET /health` on the running dev server (`:8000`) | 200 `{"status":"ok"}` |
| `GET /ready` on the running dev server | 200 database ok, redis ok, worker running |
| `GET /api/v1/products` with `X-Tenant-Domain: not-a-store` | 404 `tenant_not_found` |
| `GET /api/v1/products` with a token whose tenant id does not match the domain | 401 `invalid_token` |
| `POST /api/v1/inventory/products` with no tenant header (TestClient host `testserver`) | 404 `tenant_not_found` |

Audit rows whose SKU started with `AUDIT-` were deleted after the measurements, including their stock movements and inventory levels. Eight rows were removed.

## Not tested, and why

Each of the 652 operations was not called. Doing that safely needs a fixture for every permission, capability, and request body. The existing suite is the regression net for those paths, and only the files listed above were run here.

Not exercised: photo upload after create, concurrent creates, production data, and a full pass of the 686 tests. A selling rate inside the integer limit on this tenant creates a product and the follow-up catalog read returns it.
