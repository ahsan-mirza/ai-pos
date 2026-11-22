# O6 security and threat model

## Enforced

- Tenant and branch come from the device row and the signed-in user, not from an unsigned client claim alone.
- `inventory:adjust_stock` is required to issue, release, or quarantine. Cashiers do not have that permission.
- The sale device must be the allocation's device, with the same thumbprint and branch.
- The manifest signature uses the O2 Ed25519 key and purpose `stock_allocation`.
- Unknown keys, tampered payloads, and other terminals are rejected on the register.
- Two concurrent issuers cannot both reserve the same units. The executed SQLite test left reserved quantity at 60 when two writers each asked for 60 from 100.
- A serial is refused for a second holding allocation.
- A lot is refused when the requested quantity overlaps quantity already held on that lot.
- The client cannot raise `quantity_allocated`. There is no local setting that adds stock.

## Not proved here

- PostgreSQL row-level security with `ai_pos_app`: **NOT RUN**.
- A second tenant's HTTP session against this API: **NOT RUN**. The tests run with tenancy disabled on SQLite. Branch and device mismatches were executed.
- Native window acceptance: **NOT RUN**.
- DPAPI does not stop someone who can restore an old copy of the register database. See the recovery note.

## Unchanged

Pharmacy offline medicine checkout stays blocked. Card, QR, and pay-later still need a verified provider `PAID` result. Staff administration was not added. `single_terminal_offline_stock_enabled` still returns false. Multi-terminal safety is the allocation grant, not a claim that every offline till can sell the branch quantity.
