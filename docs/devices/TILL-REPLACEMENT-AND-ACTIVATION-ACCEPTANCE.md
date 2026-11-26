# Till replacement, registration, and activation

Date: 27-11-2026

Status: **PASSED WITH LIMITATIONS**. Nothing was deployed.

Business Pro → Registers uses the existing device, activation, and plan-seat services. Release retires the till and frees its seat. It does not delete the device row, sales, cash movements, audit rows, or invoice sequences.

## What a manager can do

- Register a till with a code, a name, and a branch. The invoice series is the existing `{branch}-{register}` series. The form shows that series and the package seats before save.
- The device identity is created when the new till exchanges the one-time activation key. The form does not accept another till's device key.
- Activate shows the business code and the single-use key. Generating a new key expires the previous unused key. A used, expired, or released key is rejected.
- Each row can be revoked or released. Both ask for confirmation. Both refuse while that till's latest queue report is still above zero, and neither deletes history.
- Status is Active (seen in the last 10 minutes), Offline, Activation pending (never connected), or Revoked.
- Creating a till, rotating a revoked till back, or activating a revoked till checks the plan cap. The seat count drops only after the retire request commits. A direct `POST /api/v1/devices` at the cap returns `plan_limit`.

The server learns about unsynced work from the till's `X-Pending-Sales` report on settings (kept for 15 minutes). It cannot read the till's SQLite queue. A till that has not reported is not blocked. The POS still refuses to accept a replacement activation on that machine while its own queue is non-empty.

## Acceptance

| # | Check | Result |
| --- | --- | --- |
| 1 | Register the first till | PASSED. `POST /api/v1/devices` returns the till as Activation pending. |
| 2 | Activate it on a real disposable POS device | NOT RUN. API activation with a generated device key passed. No physical till was enrolled. |
| 3 | Reach the package limit | PASSED. Cap forced to 1. Capacity returns `used: 1, available: 0`. |
| 4 | Another registration is blocked | PASSED. Direct `POST /api/v1/devices` returns `plan_limit` and tells the caller to release a till or upgrade. |
| 5 | Release the existing till | PASSED. `POST /api/v1/devices/{id}/release` sets `revoked_at`, expires an unused activation key, and records `device.release` with the user, branch, and time. |
| 6 | Register a different machine | PASSED. After release, a new code is accepted and gets its own series. |
| 7 | Activate the replacement | PASSED on the API. The new key binds that new till, branch, and a new device identity. Native entry of the key on a POS build was NOT RUN. |
| 8 | Old device revoked, new device active | PASSED. The old token is `device_revoked`. The old activation key is `activation_invalid`. Copying the old device public key onto the new till returns `device_binding`. The new till is Active after it connects. |
| 9 | Invoice history and numbering stay | PASSED. The sale row, cash-movement count, and `DT-01-REL1` sequence value were unchanged. The replacement uses `DT-01-REL2`. |
| 10 | No permission, and pending sync, cannot release | PASSED. A cashier receives 403. A till that reported 2 pending sales cannot be released, and the sale remains. The same report blocks a replacement activation without consuming the key. |

Rotating the released till back on while the package is full also returns `plan_limit`, so a key rotation cannot put the tenant over the cap.

## Tests run

- `apps/api/tests/test_till_release.py` (3 tests)
- `apps/api/tests/test_foundations.py::test_device_keys_scope_registers_to_their_store`
- `apps/api/tests/test_permanent_entitlement.py`
- `apps/api/tests/test_freemium.py::test_a_free_register_can_sell_and_a_locked_store_can_still_sync_the_sale`
- `apps/web` vitest: `src/features/registers/status.test.ts`, `src/features/registers/businessCode.test.ts`

11 API tests and 8 web tests passed.

## Not run

- Activation on a real disposable POS install, including typing the key into the native screen.
- The POS local block that refuses a new activation while that machine's own SQLite queue is non-empty. The function is unchanged (`replacement_block`).
- Business Pro Registers in the browser. The dev session was on the login screen, so the new form, confirmation, and Release button were not clicked. The page compiled in the running Vite dev server.
- Super Admin. It has no till-release screen. The cap is the same plan limit the tenant API reads. No Super Admin test was run for this change.
- A cross-branch user was not added. Release uses the existing store-scope check.
- Production was not deployed.
