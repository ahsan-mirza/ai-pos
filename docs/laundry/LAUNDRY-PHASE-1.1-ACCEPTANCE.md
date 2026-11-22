# Laundry Phase 1.1 acceptance

Date: 21 November 2026

Phase 1.1 catalog and database acceptance was run on a disposable PostgreSQL 18 cluster. The developer database, the inventory acceptance database, and production were not migrated.

## Result

**COMPLETE WITH LIMITATIONS**

The section 6 gates passed: fresh and repeat migration, downgrade, real `ai_pos_app` RLS, tenant and branch isolation, Business Pro `/laundry` in a browser, catalog CRUD, piece and kilogram quotes, and price-list restrictions. Grocery tenant data was unchanged.

Two items are not closed:

- An accepted pricing snapshot cannot be proven immutable until an order exists. That check moves to Phase 2.
- `developer_env_loaded=false` is a register diagnostic. The laundry API loaded only `.env.laundry-acceptance`. The acceptance register was not launched, so that file was not written.

## Environment

| Item | Value |
| --- | --- |
| API | `http://127.0.0.1:18082` |
| Business Pro | `http://127.0.0.1:5174` |
| PostgreSQL | `127.0.0.1:55821` |
| Operational database | `axizpos_laundry_acceptance` |
| Control database | `axizpos_laundry_acceptance_control` |
| Upgrade-from-previous database | `axizpos_laundry_from_0120` |
| Application login | `ai_pos_app` |
| Loaded env file | `.env.laundry-acceptance` only |
| Developer database used | no |

The running developer API and the running Business Pro dev server were left on their existing ports. Laundry used a second API and a second Vite process.

`ai_pos_app` is `LOGIN`, not a superuser, and `NOBYPASSRLS`. Evidence used a real login session. `SET ROLE` was not used.

Tenant middleware is on because the control database URL is set. `127.0.0.1` is not a tenant slug, so the API default tenant is `laundry-a`. Grocery requests used `X-Tenant-Domain: grocery-b`.

## Migration `20261121_0121`

| Check | Result |
| --- | --- |
| Documented previous revision | `20261119_0120` |
| Fresh operational upgrade | `20261121_0121` |
| Repeat upgrade | passed |
| Upgrade from `20261119_0120` | passed |
| Downgrade to `20261119_0120` | passed, then upgraded back to head |
| Grocery brand `Grocery Kept` | still present after upgrade and downgrade |
| RLS enabled and forced | all laundry catalog tables |
| Control head | `control_0041` |

Foreign-key names were shortened to the 63-character PostgreSQL limit before this successful run. The revision had never been applied, so the same revision was corrected.

## RLS

Login: `current_user = session_user = ai_pos_app`.

| Check | Result |
| --- | --- |
| Missing tenant context | 0 laundry service rows |
| Laundry Tenant A | sees its own service |
| Grocery Tenant B | sees 0 of those rows |
| Tenant B update of Tenant A | 0 rows |
| Tenant A moving a row to Tenant B | SQLSTATE `42501` |
| Cross-tenant insert | SQLSTATE `42501` |
| Grocery brands before and after | 5 and 5 |
| Grocery laundry services | 0 |

Branch and customer price lists are same-tenant rows, so RLS allows them. The application rejects the wrong branch, the wrong customer, an expired list, and a future list with `expired_price_list`.

## Business Pro `/laundry`

Signed in as the laundry tenant and used the page at `/laundry`.

| Action | Result |
| --- | --- |
| Enable dry cleaning and wash-and-fold | saved |
| Disable commercial laundry | saved; only wash-and-fold remained |
| Small shop, dry cleaner, multi-branch, commercial templates | each returned HTTP 200; the last template left commercial laundry and wash-and-fold, and the shared services were present |
| Category "Shirts" | created |
| Service "Shirt finishing" at 1500 cents | shown as 15.00 |
| Edit | "Shirt finishing plus" at 18.00 |
| Deactivate | shown Inactive |
| Search "finishing" with active only | no rows |
| Search including inactive | the inactive service |
| Standard, branch, customer, and expired lists | shown with the saved kind and end date |
| Branch A capacity 5, Branch B capacity 0 | saved |

Grocery cannot open the laundry API: `GET /api/v1/laundry/services` as grocery returned 403. The laundry page listed only laundry-a services.

## Pricing

Tax came from the tenant tax settings: UAE, standard rate 500 basis points. The quoted services store `price_includes_tax = false`, so the engine adds tax. Totals are integer cents. The browser total matched the API.

| Case | Browser | API cents |
| --- | --- | --- |
| 1 piece at 1000 | 10.50 tax 0.50 | total 1050, tax 50 |
| 2 pieces, extras 100, discount 50, express 250 | 24.15 tax 1.15 | total 2415, tax 115 |
| Counter list, quantity 2 at 1500 | 31.50 tax 1.50 | total 3150, tax 150 |
| Branch A list | 18.90 tax 0.90 | total 1890, tax 90 |
| Hotel customer list | 12.60 tax 0.60 | total 1260, tax 60 |
| 2.250 kg at 1000 cents/kg | 23.63 tax 1.13 | total 2363, tax 113 |
| 0.750 kg below the 2000 cent minimum | 21.00 tax 1.00, minimum applied | total 2100, tax 100, minimum true |

Rejected in the browser and by the API:

| Case | Result |
| --- | --- |
| Expired list | "That price list cannot be used for this branch, customer, or date." |
| Future effective date | `expired_price_list` |
| Wrong branch | `expired_price_list` |
| Wrong customer | `expired_price_list` |
| List with no rate | `missing_rate` |
| Express at Branch B capacity 0 | "Express service has no remaining capacity." |
| Express at Branch A capacity 5 | total 2153 cents (1800 + 250, tax 103) |
| Net weight zero, equal, or negative | "Net weight must be greater than zero." The request was not sent |

Capacity greater than zero is stored and allows the quote. Orders do not exist yet, so a quote does not consume a slot. That consumption check belongs to Phase 2.

A later catalog price change cannot be compared with an accepted order snapshot until Phase 2 stores one.

## Not done

No production deployment. No migration of the developer database, the inventory acceptance database, or any shared tenant database.
