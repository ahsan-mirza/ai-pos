# Stage 3F release checklist

Two results. They are not combined.

Software implementation: `TECHNICALLY COMPLETE WITH LIMITATIONS`

Production authorization: `APPROVAL PENDING`

## Technical completion

| Item | State |
|---|---|
| Backend receiving, FEFO, release, quarantine, recall, transfer, supplier return | Sqlite pharmacy tests passed in 3F.1 (63, with returns and FEFO). Portal UI was not clicked. |
| Customer return of a medicine | Restock of a released layer is now quarantined. Sqlite test passed. Whole layer is held. |
| Windows register offline block and invoice continuity | Passed in Stage 3E.6.1. Not repeated. |
| Tenant cache isolation | Passed in Stage 3E.6.1. Not repeated. |
| Header session states | Label rules unit-tested, including pending count on connection restored and a failed-sync label. Not captured on a window. |
| Double-click Charge | In-memory lock exists. Not live-tested. Server duplicate sale id is rejected by existing tests. |
| PostgreSQL concurrency races | FEFO, release, and governance races passed on a disposable database. Supplier-return, customer-return, multi-line rollback, and recall-versus-sale races were not run. Race sessions used the container superuser. |
| RLS | `ai_pos_app` login on the disposable database: empty tenant and the other tenant saw nothing; an insert without a tenant failed; the owning tenant saw its row. |
| Migrations | Disposable upgrade from empty to `20261119_0120`. Downgrade and re-upgrade passed inside the release and governance races. |
| Monitoring, backups, restore | Not rehearsed. |
| Installer signing | `BLOCKED — CERTIFICATE REQUIRED`. `AXIZPOS_SIGN_THUMBPRINT` is unset. |
| Deployment | Not done. |

## External approval

| Item | State |
|---|---|
| Regulatory policy approval | Pending |
| Pharmacist licence verification | Pending. No source connected. |
| Natural-person identity verification | Pending. Account ids are not persons. |
| Separation-of-duties approval beyond two accounts | Pending |
| Damaged-stock policy | Pending. Option A is the recommendation only. |
| Customer-return resale approval | Pending. Returned medicine is held. No resale policy was invented. |
| Release, quarantine, and recall procedure approval | Pending |
| Legal and commercial claims | Pending. Do not claim regulator notification, licence verification, or production readiness. |

Software tests do not close any row in the external table.
