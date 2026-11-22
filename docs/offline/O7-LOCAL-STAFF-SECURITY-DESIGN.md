# O7 local staff security design

A staff member created on a register is usable on that register immediately and nowhere else until the server accepts the change.

## Who may manage staff

The check is in `apps/desktop/src-tauri/src/staff.rs` `assert_actor` and again in `apps/api/app/services/staff_provision_service.py`. The settings screen hides Staff & Access unless `canManageStaff` is true. Hiding the section is not the authorization check.

| Actor | May create on this register |
| --- | --- |
| Store Manager | Cashier, and only at the manager's own branch. |
| Super Admin (tenant) | Cashier or Store Manager, inside the tenant. |
| Cashier | Nobody. The user does not hold `users:create`. |
| Any register role | Not Super Admin. Not Platform Super Admin. |

A Store Manager cannot grant a permission the local ceiling does not already list. The local ceilings are:

- Cashier: `pos:access` only.
- Store Manager: `pos:access`, `users:create`, `users:update`, `inventory:adjust_stock`.

Those local lists are smaller than the server role. The server still assigns the real system role and runs `_assert_can_grant` against that role's full permission set. A Store Manager who does not hold every Cashier permission is refused with `privilege_escalation`. The existing online `POST /api/v1/users` path is unchanged.

Branch scope: the local actor store must equal the staff store. On the server, `_assert_store_scope` refuses a store-scoped actor who names another branch (`store_scope`).

## Seats

Local creation counts `cached_users` rows with `is_active = 1` and `provisioning_status != 'rejected'`. Pending staff consume a seat. Rejected and disabled staff do not. A missing seat limit refuses creation: "Staff seats need a trusted entitlement. Connect this register and try again." The register cannot raise the number. Repeating a create after the count has reached the limit does not insert another user.

The server ignores any client-supplied cap. It counts active `users` and calls `assert_room(used, "staff")`. When `limit_value("staff")` is `None`, the server does not cap. When the plan cap is already reached, the response is 409 `plan_limit`, the new user is not inserted, and a rejected provisioning row is kept.

## Credentials

`create_local` hashes with the existing `hash_pin`. The plaintext PIN is not written to `cached_users`, `staff_provisioning`, or `staff_audit`. The payload field is `pin_verifier`. A verifier that is not an Argon2 PHC string is refused locally if it contains the PIN, and refused by the server unless it starts with `$argon2id$` and fits `hashed_pin`. The server stores that string in `users.hashed_pin`. It does not re-hash it with scrypt, and it does not accept a plaintext `pin` field (`StaffProvisionIn` has no such field).

`finish_offline` refuses `is_active = 0` and `provisioning_status = 'rejected'` before it checks the PIN. Pending staff with `pos:access` can unlock the originating register. Five wrong PINs still lock the account. The attempt counter is the existing `failed_attempts` / `locked_until` pair, which is stored in SQLite and therefore survives a restart of that database file.

The user row, the provisioning event, and the audit row commit in one SQLite transaction. A failed write does not leave a usable user without those rows.

## What this design does not do

- It does not issue an access token. Online APIs still require the existing bearer token.
- It does not put staff verifiers in the product bootstrap.
- It does not change sale or return `sync_queue` rows.
- It does not change `inventory_levels`, `stock_movements`, or O6 allocation signatures.
- It does not let a disabled or rejected cashier spend an allocation they could not already spend. Allocation checks stay in the O6 path.
- Server `verify_pin` still does not understand Argon2. Another register verifies the pulled verifier with the desktop Argon2 check. An online `login-pin` of that verifier against the API is not supported in this phase.
