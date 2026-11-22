# Laundry Phase 2.1 order intake closure

Date: 21 November 2026

Phase 2.1 closed the cross-client, payment, photo, tag, offline, and concurrency gaps on the disposable laundry database. The developer database, the inventory acceptance database, and production were not migrated.

## Result

**COMPLETE WITH LIMITATIONS**

## Environment

| Item | Value |
| --- | --- |
| API | `http://127.0.0.1:18082` |
| Business Pro | `http://127.0.0.1:5174` |
| Register preview | `http://127.0.0.1:1421` |
| Operational database | `axizpos_laundry_acceptance` on `127.0.0.1:55821` |
| Control database | `axizpos_laundry_acceptance_control` |
| Tenant | `laundry-a` |
| Branch used | Branch A |
| Application login | `ai_pos_app`, `LOGIN`, not superuser, no row-level-security bypass |
| Migration head | `20261121_0122` |
| Register identity | browser preview device `laundry-acceptance-01` |

The installed production register was not used. Existing orders `LD-4844E6D1` and `LD-330B1622` were left in place and were not treated as a synchronization pair.

## Same-order synchronization

### Register to Business Pro

The register created `LD-4F3A07CA`. Business Pro opened that same code. Both showed:

- Customer Hotel Account
- Branch A
- Garments: White shirt, dry clean, quantity 1, condition tear; Blue shirt, press, quantity 1, condition missing button
- Tags `LD-4F3A07CA-01` and `LD-4F3A07CA-02`, both active
- Accepted unit price 1000 cents at 500 basis points
- Total 10.50, tax 0.50, paid 5.00, due 5.50
- Operational status TAGGED
- Instructions “Call when ready”

### Business Pro to register

Business Pro created `LD-7B77A286`. The register lookup loaded that same code:

- Customer Walk-in Customer
- Branch A
- Green shirt, dry clean, quantity 1, condition fading
- Tag `LD-7B77A286-01` active
- Total 10.50, tax 0.50, paid 0.00, due 10.50
- Status TAGGED

The second screen did not create a replacement order.

## Payments

The 10.50 order took a 5.00 cash deposit at intake. Both clients showed paid 5.00 and due 5.50. The held deposit is the existing laundry deposit row, counted with the drawer the same way as a repair deposit. It is not a second tender ledger and not a tax invoice.

Automated coverage on top of that screen:

- A repeated deposit id does not add the money again
- A payment above the balance is rejected
- A second method can pay the remainder, after which the balance is 0 and the status is PAID

## Offline

With the acceptance API stopped, the register stored one draft in the acceptance browser queue and showed “Local pending order. It is not a server invoice.” The local id was `9584f748-311c-4ad3-9be4-b8c13697f8d3`. No `LD-` code was shown. Reloading the register left that draft in place.

After the API returned, one sync created `LD-9584F748`. Business Pro showed Hotel Account, Branch A, the offline shirt and the second garment, total 10.50, paid 0.00. The queue was then empty, so a later open did not submit it again. The automated sync test also returns `duplicate` for the same event.

Express orders and deposits are refused offline. The installed register’s on-device queue was not used. After the reload, the in-memory sign-in token was gone, so the till reported that a signed-in user was required while reading the accepted order back. The server had already stored it.

## Tags and receipts

The register rendered a QR for `LD-4F3A07CA-01` and opened the browser print path. Reprint records an event and keeps the same tag. The intake slip is labeled as not a tax invoice and not a payment receipt. A separate payment slip is offered only when money has been taken. No physical printer was attached.

## Photos

A JPEG was uploaded from the register onto `LD-4F3A07CA`. Business Pro displayed the stored image for that order. The API checks the declared type against the file bytes. A PNG label on JPEG bytes is rejected. Photos are appended. They are not replaced.

## Concurrent edits

Two password sessions edited one new order at the same version at the same time. The responses were 200 and 409. The stored garment kept the first description, “Pressed”, and the original condition, “tear”. The version moved from 1 to 2.

## Security

`acceptance/laundry/prove_order_rls.py` against `ai_pos_app`:

- Laundry tenant saw 6 orders
- Grocery tenant saw 0
- A cross-tenant insert and a tenant move both returned SQLSTATE `42501`
- Result PASSED

Cashier and Store Manager system roles still do not include the laundry order permissions.

## Tests

Command:

`node scripts/python.mjs -m pytest tests/test_laundry_orders.py tests/test_laundry_catalog.py -q`

Result: 9 passed.

That run covers catalog quotes, order creation, same-order read by a second session, repeated submit, deposit replay, overpayment, split settlement, garment conflict, photo bytes, tag reprint without a new tag, and one offline sync that stays a duplicate on the second push.

The register and Business Pro checks above were done in the browser. There is no separate frontend unit-test run for these screens.

## Known limitations

- The acceptance register is the browser preview with its own local queue. It is not the installed Windows register.
- After a reload, sync can accept the draft before the till has a user token to display the new server code.
- Tag and receipt output uses the browser print dialog. A configured thermal printer was not present.
- The business currency on this acceptance tenant is still USD. Amounts are integer cents.
- Production, delivery, and claims are still status and history only.

No production deployment and no migration of the shared developer or inventory acceptance databases.
