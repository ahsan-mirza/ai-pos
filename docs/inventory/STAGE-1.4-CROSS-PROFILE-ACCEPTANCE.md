# Stage 1.4 — Cross-profile acceptance

Date: 19 November 2026. No separate disposable tenant was created for fashion, electronics, restaurant, cafe, quick service, or a new pharmacy stack. The grocery acceptance tenant `inv-accept` and the existing pharmacy inventory tenant row were left in place.

## Grocery tenant already on the disposable database

| Check | Result |
|---|---|
| Oats product, one row, Store A quantity 2, one opening movement | Holds |
| `INV-TIN` unchanged | Holds |
| Medicine product belongs to the other tenant and is absent from the grocery product list | Holds |
| Floor Manager can list categories, including Acceptance Dry Goods and Produce | HTTP 200 |
| Floor Manager cannot create a category | HTTP 403, store scope |
| Catalog admin can create and delete a category | 201 then 204, probe category removed |
| Duplicate SKU | HTTP 409 |
| Enrolled device can list products and cannot list stock | 200 and 403 |
| Cashier PIN can sign in and cannot list stock | 200 and 403 permission |
| Grocery schema | `Produce` matches the grocery specification template. `Acceptance Dry Goods` does not, so it keeps custom specification rows. A live category switch was not performed. |

## Not run

Fashion season, collection, gender, and variant matrix were not exercised on a fashion tenant. Electronics serial and IMEI sale and transfer were not exercised on an electronics tenant. Restaurant, cafe, and quick-service inventory were not opened. Pharmacy lot release, recall, quarantine, and offline sale block were not re-run in this stage; those rules remain in the pharmacy services and were not weakened.

Offline grocery sale, queue replay, and restart recovery were not run. The acceptance register was not launched.

## Status

Business profile acceptance: **NOT RUN** beyond the grocery API checks above.
