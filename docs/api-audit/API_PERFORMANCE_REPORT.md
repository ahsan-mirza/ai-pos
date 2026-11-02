# API performance report

Measured on 2026-11-02 against the local development database and the running API on `127.0.0.1:8000`. This is one tenant with **2** products. It is not a production load test and it is not a percentile claim. Eight writes and one list call are too small a sample for P95 or P99.

## Product creation

`POST /api/v1/inventory/products` through an in-process client, eight sequential creates, each with opening stock of 1. Times in milliseconds, in order:

`204.7, 57.3, 47.4, 50.0, 52.6, 51.4, 52.1, 50.6`

Minimum 47.4. Median 51.8. Maximum 204.7 on the first call. The later calls sit around 50 ms. The engineering target in the brief (under 500 ms) is met by every sample in this environment.

## Reads

| Call | Samples | Time | Notes |
| --- | ---: | ---: | --- |
| Tenant-scoped `SELECT id FROM products WHERE tenant_id = … ORDER BY name, id LIMIT 50` | 1 plan | 0.038 ms execution | Index scan on `ix_products_tenant_id`, 2 rows, buffers shared hit 9 |
| `GET /api/v1/products?limit=50` | 1 | 508.7 ms | In-process client. Returns 2 products. Includes auth, stock totals, price lists, and image lookup |
| `GET /health` in-process | 1 | 29.3 ms | |
| `GET /health` on the running server | 1 | not timed | Body `{"status":"ok"}` |
| `GET /ready` on the running server | 1 | not timed | 200, database ok, redis ok, worker running |

The list endpoint's wall time is far above the SQL time. One sample cannot say whether that 509 ms is cold start, Python serialization, or a join in `products_out`. It was not optimized, because there is no repeated measurement to compare against.

## What was not run

No concurrent load, no sustained load, and no production traffic. Requests per second and error rate under load were not measured. Browser and network time are not included; the figures above are inside the API process or on localhost.
