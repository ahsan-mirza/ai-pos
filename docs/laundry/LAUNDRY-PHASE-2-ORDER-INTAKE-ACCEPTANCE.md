# Laundry Phase 2 order intake acceptance

Date: 21 November 2026

Phase 2 adds laundry orders on the disposable acceptance database only. The developer database, the inventory acceptance database, and production were not migrated.

## Result

**COMPLETE WITH LIMITATIONS**

Business Pro and the register preview each created a live order against `http://127.0.0.1:18082`. The installed Windows register and its offline queue were not used.

| Area | Result |
| --- | --- |
| Backend | COMPLETE WITH LIMITATIONS |
| POS | PASSED WITH LIMITATIONS |
| Business Pro | PASSED WITH LIMITATIONS |
| Pricing | PASSED |
| Garment and tag management | PASSED |
| Security and RLS | PASSED |
| Offline synchronization | NOT RUN |
| Automated tests | 8 laundry tests passed |
| Runtime acceptance | Both UIs accepted an order on the disposable API |
| Production deployment | not done |

## Backend

Migration `20261121_0122` revises `20261121_0121`. It was applied to `axizpos_laundry_acceptance` on `127.0.0.1:55821`. Head after the upgrade: `20261121_0122`.

Orders, garments, bags, tags, tag events, photos, order events, and held deposits are separate tables. Each is tenant scoped and has forced row-level security. Operational status, garment stage, payment status, collection status, and claim status are separate columns.

Pricing calls the existing laundry quote service and the existing tax helper. The accepted quote is stored on the order. A later catalog rate change does not change that snapshot. Deposits are held rows, counted in the drawer the same way as repair deposits. Garment work is not posted through a stock-moving sale.

`tests/test_laundry_orders.py` and `tests/test_laundry_catalog.py`: 8 passed.

Covered by those tests:

- Walk-in intake with a garment, a weighed bag, condition text, and a cash deposit
- Repeated submit with the same idempotency key returns the same order
- Catalog price change leaves the stored total and unit price
- JPEG photo accepted, PNG bytes labeled as PNG rejected
- Tag scan, repeated scan, unknown tag, wrong order, and replaced tag
- Express capacity of 1 accepts the first order and rejects the second
- Quantity edit before production, reason required after production, cancellation keeps the created event
- Cashier and Store Manager system roles do not include the laundry order permissions

## Business Pro

`/laundry/orders` was opened in the browser against the disposable API.

A walk-in order for Walk-in Customer at Branch A, one dry-clean shirt, with a 5.00 cash deposit, was accepted by the server:

- Code `LD-4844E6D1`
- Total 10.50, tax 0.50, paid 5.00, due 5.50
- Accepted unit price 1000 cents at 500 basis points
- Garment stage TAGGED, condition tear
- Tag `LD-4844E6D1-01` active
- Timeline event `created`

The page reads and writes the live API.

## POS

The register preview at `http://127.0.0.1:1421` signed in with the laundry admin PIN and opened Laundry intake. Customers came from the register customer sync. Services came from the laundry catalog. The signed-in user is a super admin, so the preview asked for the intake branch.

A walk-in order for Walk-in Customer at Branch A, one dry-clean shirt, condition “missing button”, was accepted by the server:

- Code `LD-330B1622`
- Total 10.50, tax 0.50, paid 0.00, due 10.50
- Tag `LD-330B1622-01` active

The register showed those server figures. No deposit was taken on this order. Express stayed off.

Order routes accept a POS token when the user has the matching laundry permission. Cashiers and Store Managers still do not receive those permissions. Listing services from the register requires portal access or a laundry order permission, so a cashier token cannot read the catalog.

## Security and RLS

A real `ai_pos_app` session on the disposable database, with `LOGIN` and without `BYPASSRLS`, checked the order tables:

- Missing tenant context saw 0 orders
- Laundry Tenant A saw 2 orders
- Grocery Tenant B saw 0 orders
- Grocery Tenant B’s update of a Laundry order changed 0 rows
- Moving that order to the other tenant returned SQLSTATE `42501`
- Inserting a Laundry order while the session was Grocery Tenant B returned SQLSTATE `42501`
- Row-level security is forced on the eight order tables

## Known limitations

- Offline queueing runs only inside the installed register. This pass used the browser preview, so a pending order, a failed sync, and a restart were not shown.
- The register does not upload intake photos, print tags, or print a receipt. Photo checks and tag reprint or replacement passed through the API tests.
- Starting production records the status and keeps history. It is not a plant floor, delivery route, or claim desk.
- A held deposit is not an invoice and does not use a new tender ledger. The register order above took no deposit. The Business Pro order took a cash deposit.
- Express capacity is counted per branch per UTC day. It is not a timed slot board.
- Two cashiers editing one order at the same time was not driven in the browser. The API returns a conflict when the version does not match.
- The acceptance business currency stayed USD. Tax used the configured 500 basis point rate, added because the service price does not include tax.

No production deployment and no migration of the shared developer or inventory acceptance databases.
