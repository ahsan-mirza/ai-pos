# O8.2 Staff and Access acceptance

Status: **PASSED WITH LIMITATIONS**.

The Staff & Access screen was not opened. No store-manager click, PIN entry, or register restart was performed on a window. The evidence is the API and the desktop library.

## Executed

Desktop library, inside the 53 tests:

- `a_local_cashier_is_pending_and_the_pin_is_not_stored`
- `disablement_survives_a_rejected_provisioning_event`
- `another_terminal_receives_the_verifier_only_after_acceptance`
- `five_wrong_pins_lock_the_local_cashier`

API, inside the 28 tests in 27.37s (`tests/test_staff_provision.py`):

Create, edit, PIN reset, disable, role refusal, store scope, seat limit, duplicate and conflicting events, the staff feed, and Argon2 `login-pin` are in that file. `GET /users` does not return the verifier. The feed returns an `$argon2id$` verifier only to a device principal.

Vitest `staffAccess.test.ts`: 2 passed. That covers the role ceiling and the PIN shape used by the form. It does not click the panel.

## Credential design

Online PIN login is supported. `verify_pin` verifies a stored `$argon2` verifier and still verifies the older peppered scrypt form. The desktop cache stores the Argon2 verifier, not the PIN. A second credential system was not added.

The register form and `POST /api/v1/users/provision` do not create Super Admin or Platform Super Admin. Store Manager may create Cashier. Tenant Super Admin may create Cashier or Store Manager. Pending staff stay on the originating terminal until the server accepts them and another terminal imports the feed.

## Not run on a window

Login as Store Manager, create, edit, PIN reset, disable, failed unlock, restart, reconnect, and login on a second register were not clicked. Those steps stay NOT RUN as a native UI acceptance. The library and API results above are the ones that ran.
