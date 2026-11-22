# O7 roles and delegation

Role names are the existing system names. O7 does not add a role.

## Ceiling on the register

`permissions_for` and `assert_actor` in `apps/desktop/src-tauri/src/staff.rs`:

- A Store Manager may request Cashier only, and only for the same branch string.
- A Super Admin may request Cashier or Store Manager.
- Super Admin and Platform Super Admin are not roles this register can grant. The error is "This register cannot grant that role."
- Any other actor receives "You cannot manage staff."
- A manager cannot disable their own local user id.

The settings screen uses the same idea in `canManageStaff` (`apps/desktop/src/features/settings/staffAccess.ts`). Cashier and Platform Super Admin see no Staff & Access section. Store Manager and Super Admin see it only when `users:create` is present. The server still checks the token.

## Ceiling on the server

`provision` in `staff_provision_service.py` does not trust the offline decision.

- `role_name` must be `Cashier` or `Store Manager`. `Super Admin` and `Platform Super Admin` return 403 `role_not_allowed`.
- The signed-in user's role must be Store Manager or Super Admin.
- A Store Manager who asks for Store Manager is refused, even though `_assert_can_grant` would allow a person who already holds every Store Manager permission. That stricter rule applies only to `POST /users/provision`. The existing online user API is unchanged.
- `_assert_can_grant` still runs against the system role's permission set. Extra permissions the actor does not hold return 403 `privilege_escalation`.
- `_assert_store_scope` still confines a store-scoped actor to their store.

A tenant Super Admin is the existing Super Admin role. They are not given a new permission, and they cannot name another tenant. Tenant isolation remains the existing tenant session. These tests run in the single in-memory tenant.

## What the local user is allowed to do after creation

A pending cashier has only `pos:access` on that register. They can unlock it. They do not gain portal, platform, or inventory-allocation rights from the staff event. A pending Store Manager, created by a Super Admin, has the four local permissions listed above and not the rest of the server Store Manager set until a later online session loads the server role.

`inventory:adjust_stock` on that local list does not call the allocation service and does not increase a terminal remainder.
