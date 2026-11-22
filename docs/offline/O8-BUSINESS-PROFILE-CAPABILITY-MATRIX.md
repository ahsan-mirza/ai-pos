# O8 business-profile capability matrix

Profiles are the ones in `apps/desktop/src/features/inventory/tabs.ts`: Grocery, Electronics and Wholesale, Wholesale and Retail, Fashion and Retail, Restaurant, Cafe, Quick Service, Pharmacy, and Laundry.

Statuses: `SUPPORTED_OFFLINE`, `SUPPORTED_WITH_LIMITATIONS`, `REQUIRES_ONLINE`, `BLOCKED_OFFLINE`, `NOT_IMPLEMENTED`, `NOT_TESTED`.

A shared cart test is not profile acceptance. O8.11 filled Downtown Till A's signed menu and floor tables and settled takeaway #3E55 as cash invoice `O810-DTA-000001`. Restaurant Native UI stays `SUPPORTED_WITH_LIMITATIONS` because dine-in, delivery, and a second till were not completed. O8.10 opened `com.axizpos.restaurant.acceptance` on Downtown Till A. The menu showed O810 Grill and a takeaway ticket was started. O8.9 enabled the Restaurant preset through the business-wide owner on disposable Postgres. O8.8 explained the order-list 403 as the Open orders module being off. O8.7 created cashier `o85till2` on that grocery register and accepted it on the disposable API. The shell is still `com.axizpos.pharmacy.acceptance` and the business profile is `grocery`. The other profiles stay `NOT_TESTED` in the Native UI column.

| Profile | Activation | Unlock | Catalogue | Pricing and tax | Checkout | Payment | Inventory | Serial, lot, weight | Returns | Staff | Native UI |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Grocery | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Cash SUPPORTED_WITH_LIMITATIONS. Card, QR, and pay-later REQUIRES_ONLINE | SUPPORTED_WITH_LIMITATIONS | Weight path exists. Lot and FEFO NOT_TESTED in this run | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS. O8.5 cash, allocation, overdraw, and sync on O85 Grocery. Weight, bag fee, and FEFO not walked |
| Electronics and Wholesale | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Customer credit REQUIRES_ONLINE | Serial allocation rules exist in O6 tests. This run did not sell a serial on a window | NOT_TESTED as a full profile | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Wholesale and Retail | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Credit REQUIRES_ONLINE | Same allocation library | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Fashion and Retail | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Card REQUIRES_ONLINE | Allocation applies to stock-tracked variants | Variant sale NOT_TESTED on a window | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Restaurant | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Menu items that are not stock-tracked do not use allocation | Card REQUIRES_ONLINE. Kitchen printer NOT_TESTED | Stock-tracked lines use allocation when offline | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS. O8.11 committed Downtown menu and floor rows and settled takeaway #3E55 as cash. Dine-in, delivery, and a second till were not completed |
| Cafe | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Same food shell as Restaurant | Card REQUIRES_ONLINE | Same as Restaurant | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Quick Service | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Same food shell | Card REQUIRES_ONLINE | Same as Restaurant | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Pharmacy | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Catalogue download does not unlock a medicine sale | SUPPORTED_WITH_LIMITATIONS | BLOCKED_OFFLINE | REQUIRES_ONLINE | A valid allocation does not unblock medicine checkout | BLOCKED_OFFLINE for medicine | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |
| Laundry | SUPPORTED_WITH_LIMITATIONS | SUPPORTED_WITH_LIMITATIONS | Orders stay on the laundry order API. Retail Checkout is not the laundry screen | Server prices | A non-express order with no deposit can be queued by existing code. This run did not create one. NOT_TESTED | Deposit and express REQUIRES_ONLINE | Not an allocation sale | NOT_IMPLEMENTED for garments as retail stock | NOT_TESTED | SUPPORTED_WITH_LIMITATIONS | NOT_TESTED |

Shared evidence behind the limited rows:

- Permanent entitlement and the test key exclusion: desktop library.
- Bootstrap, queue collision, and allocation consume: desktop library and API tests from earlier phases, re-run with the O8 API command.
- Offline allocation stamp: `allocation.test.ts`.
- Pharmacy block: `checkout.pharmacy.test.ts`.
- Staff create, lockout, rejection, and second-database import: desktop library. Online Argon2 PIN login: API test.

No profile is fully accepted. O8.5 ran grocery cash checkout, an offline allocation sale, an overdraw refusal, and sync on `com.axizpos.pharmacy.acceptance` for store `O85 Grocery`. Weighed sale, bag fee, and FEFO were not walked, so Grocery native UI stays limited. Electronics, Fashion, Restaurant, and Laundry were not walked. The evidence is `O8.5-NATIVE-END-TO-END-ACCEPTANCE-REPORT.md`.

O8.4 completed a grocery cash sale, an offline allocation sale, and an overdraw block on `com.axizpos.offline.acceptance`.

O8.5 inspected the restaurant code and wrote `O8.5-RESTAURANT-FEATURE-INVENTORY.md`. Local table tickets and `open_order` upload already exist. Menu and floor are a cache and an online read, not an incremental cursor. The restaurant native walk and the two-branch test were not run. Restaurant, Cafe, and Quick Service stay `NOT_TESTED` on a window.

O8.6 puts menu and floor on the existing catalogue feed and files a manager-review row when two dine-in orders use one table. The API test uses two stores in the SQLite suite, where tenancy is off. The native restaurant walk was not run.

O8.4 launched `com.axizpos.pharmacy.acceptance` and confirmed the window title, data directory, move, and restore. It did not walk Grocery, Electronics, Fashion, Restaurant, or Laundry through checkout. The Native UI column stays `NOT_TESTED`. O8.3 did not open a register window. Native UI stays `NOT_TESTED`. PostgreSQL tenant and store checks for the disposable application role are in `O8.3-TECHNICAL-LIMITATION-CLOSURE-REPORT.md`. Pharmacy medicine checkout stays `BLOCKED_OFFLINE`.

## O8.2 operation classification

O8.2 did not open a register window and did not run a profile workflow on one. Native UI stays `NOT_TESTED`. A profile is not fully accepted.

These labels apply to the shared register behaviour. They are not a per-profile pass.

| Operation | Status | Scope |
| --- | --- | --- |
| Permanent entitlement verification | SUPPORTED_WITH_LIMITATIONS | Single register, library tests. Production public key AWAITING APPROVAL |
| Offline staff unlock | SUPPORTED_WITH_LIMITATIONS | Originating terminal only until the server accepts the user |
| Server PIN check | SUPPORTED_WITH_LIMITATIONS | Online `login-pin` verifies Argon2. Not demonstrated on a window |
| Cash sale inside an allocation | SUPPORTED_WITH_LIMITATIONS | Single terminal. Library and API. Native checkout NOT_TESTED |
| Card, QR, pay-later | REQUIRES_ONLINE | Provider PAID is still required |
| Inventory allocation | SUPPORTED_WITH_LIMITATIONS | Single-terminal remainder. Two grants are isolated in API tests. Native card NOT_TESTED |
| Multi-terminal offline stock | SUPPORTED_WITH_LIMITATIONS | Safety is the O6 grant. A terminal that stays disconnected keeps its reservation. Lost-terminal write-off AWAITING APPROVAL |
| Returns | SUPPORTED_WITH_LIMITATIONS | Queue atomicity is in the library tests. Not clicked per profile |
| Pharmacy medicine checkout | BLOCKED_OFFLINE | Entitlement, allocation, staff cache, and catalogue download do not override it. Vitest still fails closed |
| Laundry order intake | NOT_TESTED | Orders remain the laundry entry. Retail Checkout is not the laundry screen. This run created no laundry order |
| Kitchen printer | NOT_TESTED | No device acceptance |
| Conflict adjustment | AWAITING APPROVAL | Not implemented |
| PostgreSQL tenant isolation | SUPPORTED_WITH_LIMITATIONS | Direct SQL as `ai_pos_app`. Store filtering applies only when `app.store_id` is set. The request session sets `app.tenant_id` only. See `O8-POSTGRESQL-RLS-FINAL-ACCEPTANCE.md` |
