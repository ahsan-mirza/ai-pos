# Inventory performance acceptance

Date: 20 November 2026. Status: **MEASURED ONLY**. The proposed targets are **AWAITING APPROVAL**.

No approved latency target was found in the repository. The measurements in `INVENTORY-PERFORMANCE-REPORT.md` are not an acceptance result. They were not relabeled.

## Measured earlier the same day

On the acceptance database, about 23 MB, one signed-in user, 20 reads:

| Call | Median | P95 |
|---|---:|---:|
| Product list | 47.2 ms | 65.8 ms |
| Product search | 47.1 ms | 58.8 ms |
| Branch stock | 47.7 ms | 53.3 ms |
| Purchase orders | 84.5 ms | 100.7 ms |
| Transfers | 46.2 ms | 65.9 ms |
| Gallery | 30.8 ms | 44.8 ms |

Five three-line draft creates took 54.3 to 86.5 ms. No errors. `pg_stat_statements` was not enabled, so query counts were not captured. These figures were not compared with an approved target because none exists.

## Approval request

The repository does not name a person. Please ask the owner of AxizPOS inventory service levels, together with the engineering owner of the API, to approve or replace the blank targets below. Until that approval is recorded in this file, performance stays **AWAITING APPROVAL** and cannot pass a release review.

| Operation | Sample | Proposed measurement | Approved target |
|---|---|---|---|
| Product list | At least 20 calls | Median and P95, with catalog size and concurrent users stated | Awaiting approval |
| Product search | At least 20 calls | Median and P95 of a name or SKU search | Awaiting approval |
| Product detail and gallery | At least 20 calls | Median and P95 | Awaiting approval |
| Purchase order create | At least 5 three-line drafts | Median of create, and cancel must not move stock | Awaiting approval |
| Receiving | At least 5 receipts | Median of a posted receipt, with movement count | Awaiting approval |
| Transfer | At least 5 transfers | Median of create, ship, and receive | Awaiting approval |
| Stock count | At least 5 counts | Median of open, record, and cancel | Awaiting approval |
| Branch stock | At least 20 calls | Median and P95 | Awaiting approval |

Each approved row also needs the catalog size, the concurrent users, and the error rate that fails the gate. Those were not set. No millisecond number in this document is an approved threshold.
