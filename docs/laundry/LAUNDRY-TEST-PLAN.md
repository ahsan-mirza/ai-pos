# Laundry test plan

## Covered in this phase

`apps/api/tests/test_laundry_catalog.py`

- Piece price plus extra and express surcharge, then the supplied tax rate.
- Kilogram price with precision 3, where 1.250 at 10.00 is below a 20.00 minimum and the minimum is charged.
- Negative quantity, zero rate, unknown unit, unauthorized discount, and a surcharge the service does not offer.
- Laundry routes refuse a business that has not enabled the capability.
- A shop template creates bag tracking and the starter services.
- A branch price is used for that branch and refused for another branch.
- A customer price is refused for a different customer.
- A list whose end date has passed is refused.
- Express is refused when daily capacity is zero.

`apps/api/tests/test_capabilities.py` keeps the TypeScript and Python catalogs, signup cards, and presets aligned.

## Not run

POS intake, tag printing, production scans, payments, refunds, claims, delivery, packages, offline sync, concurrency, multi-tenant PostgreSQL RLS with `ai_pos_app`, and performance. The migration file is present and was not applied to a live database.
