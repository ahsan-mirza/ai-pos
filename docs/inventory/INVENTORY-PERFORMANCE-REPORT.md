# Inventory performance report

Date: 20 November 2026.

No approved latency target exists, so these figures are measurements only. They are not a performance acceptance.

## Machine and dataset

- Machine: MSI Raider 18 HX, Intel Core Ultra 9 285HX, 24 cores, 64 GB RAM.
- Database: `axizpos_inventory_acceptance` on `127.0.0.1:55433`, 23 MB.
- Owner row counts after the timing drafts: 10 products, 23 stock movements, 9 purchase orders, 1 stock transfer, 5 product images.
- The five extra purchase orders are cancelled three-line timing drafts. They did not add stock movements.
- One signed-in Floor Manager. No concurrent users.
- 20 repetitions per read. P95 is the 19th value of the sorted sample. No errors.
- `pg_stat_statements` was not enabled, so query counts and lock waits were not captured. No index was changed.

## Latency

| Call | Median | P95 | Max |
|---|---:|---:|---:|
| Product list | 47.2 ms | 65.8 ms | 77.4 ms |
| Product search | 47.1 ms | 58.8 ms | 59.9 ms |
| Branch stock | 47.7 ms | 53.3 ms | 53.6 ms |
| Purchase orders | 84.5 ms | 100.7 ms | 111.8 ms |
| Transfers | 46.2 ms | 65.9 ms | 70.3 ms |
| Gallery | 30.8 ms | 44.8 ms | 45.4 ms |

Five three-line draft creates took 54.3 to 86.5 ms. Each cancel took 35.6 to 57.4 ms and returned `cancelled`.

Evidence: `acceptance/inventory/evidence/final-release/performance-and-rls.json`.

No service-level objective for inventory is recorded in the repository. The figures above were not compared with an approved target.

## Proposed acceptance matrix

This matrix is **AWAITING APPROVAL**. None of these rows is an approved target.

| Operation | What to measure | Sample | Approved target |
|---|---|---|---|
| Product list | Median and P95 of the signed-in list call | At least 20 calls, one catalog size stated | Awaiting approval |
| Product search | Median and P95 of a name or SKU search | At least 20 calls | Awaiting approval |
| Category, brand, and model lookup | Median and P95 | At least 20 calls | Awaiting approval |
| Product detail and gallery | Median and P95 | At least 20 calls | Awaiting approval |
| Multi-line purchase order | Create, save, and cancel a three-line draft | At least 5 documents | Awaiting approval |
| Multi-line receiving | Post a three-line receipt | At least 5 receipts | Awaiting approval |
| Multi-line transfer | Create, ship, and receive three lines | At least 5 transfers | Awaiting approval |
| Stock count | Open, record, and cancel a count | At least 5 counts | Awaiting approval |
| Branch stock | Median and P95 of one branch | At least 20 calls | Awaiting approval |

Each approved row also needs the catalog size, concurrent users, and the error rate that fails the gate. Those were not set.

## Status

Performance: **MEASURED ONLY**. The proposed matrix is **AWAITING APPROVAL**.
