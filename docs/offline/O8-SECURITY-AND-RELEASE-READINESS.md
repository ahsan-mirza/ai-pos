# O8 security and release readiness

## Release entitlement key

Status: **AWAITING APPROVAL**.

`entitlement.rs` `production_trusted_keys` reads `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY` at compile time. Empty or absent values produce an empty list. `trusted_keys` adds the O2 test key only when the crate is built with `cfg(test)`.

`the_test_signing_key_is_not_a_release_key` passed. No authorized production public key was supplied, and none was generated. A release binary built without those variables will reject production entitlements. That binary was not packaged and was not deployed.

The private signing seed stays on the server in the existing entitlement configuration. This run did not print it.

## Authentication

- Offline unlock still uses Argon2, five failures, and `pos:access`.
- A disabled or rejected local user is refused before the PIN check.
- `verify_pin` now verifies a stored `$argon2` string with `argon2-cffi`. Existing scrypt PINs still use the peppered scrypt path. If the Argon2 package cannot be imported, that branch returns false.
- `GET /api/v1/users` in the new test did not contain the verifier. The staff feed still returns `pin_verifier` to a device credential. It is not part of product bootstrap.
- Staff commands use the current register session and require `users:create` plus Store Manager or Super Admin. The form does not choose the actor.

## Allocation

`verified_balances` drops a row whose signature, device binding, or product id does not match. The cart then sees no remainder and blocks. `consume_allocation` still refuses an overdraw in the same transaction as the queue insert. A cashier has no override for that check.

## What was not proved

PostgreSQL RLS: **NOT RUN**. Native window: **NOT RUN**. Lost-terminal write-off and financial conflict adjustment remain **AWAITING APPROVAL**.
