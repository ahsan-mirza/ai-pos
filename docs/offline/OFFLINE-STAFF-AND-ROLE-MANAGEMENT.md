# Offline staff and role management

Phase O5 design. Status: **IN PROGRESS**. Decision C is the policy. Local staff creation is not implemented.

Date: 22 November 2026. No database was changed.

## Role map

The baseline names use the existing role and permission system. They do not add a laundry-style parallel role list.

| Baseline name | Implementation | What that account may do offline |
| --- | --- | --- |
| Platform Super Admin | Console operator in the control plane. Not a row in tenant `roles`. | Nothing on the register. The register cannot create this account. |
| Store / Tenant Super Admin | System role `Super Admin`, id `00000000-0000-4000-8000-0000000000a1` | Staff inside this tenant, within the signed snapshot. Cannot grant pharmacist appointment authority. Cannot leave the tenant. |
| Store Admin | System role `Store Manager`, id `00000000-0000-4000-8000-0000000000a2` | Staff for the register's store. The role already has `users:create`, `users:read`, and `users:update`. It does not have `users:delete` or `roles:manage`. |
| Cashier | System role `Cashier` | Sell. No staff administration. |
| Technician | System role `Technician` | The repair permissions that role already has. |

A Store Manager cannot assign `Super Admin`, cannot edit their own permissions upward, cannot select another branch, and cannot exceed the staff-seat cap in the cached entitlement. Tenant Super Admin cannot create a platform operator and cannot write another tenant. Audit rows are insert-only. Neither role gets a delete of audit history.

Delegated custom roles stay the tenant's `roles` rows. An administrator may assign only a role whose permission set is a subset of the administrator's signed snapshot.

## Local authentication that already works

`cached_users` stores `pin_hash` as Argon2 (`auth.rs`). Verification uses `Argon2::default()` and a per-user salt. Five failures set `locked_until` for five minutes. Offline unlock requires a cached user, a matching store, and `pos:access`. Session mode is `offline`. Password login remains the server path when the account is configured for it. PINs and passwords are not stored in plaintext SQLite or `localStorage`.

O5 keeps that lockout and adds session timeout, register lock, logout, and reauthentication for sensitive actions on top of the session already stored in `register_session`.

A user who has never been cached still cannot sign in until this register has the account. That includes accounts created on another till, until the server accepts them and this till pulls them.

## Signed permission snapshot

The JSON list in `cached_users.permissions` becomes a signed snapshot with:

- Version.
- User id.
- Tenant and branch.
- Delegated capabilities and permission keys.
- Issue time.
- Policy identifier.
- Device binding.

The register verifies the signature with the same public key as the permanent entitlement. A local edit of the JSON that breaks the signature disables administrative use of that snapshot. Selling permissions for an already verified snapshot remain those in the signature, not a hand-edited column.

The snapshot is refreshed by incremental pull. While disconnected, the last valid snapshot stays in force. Settings text must say that a remote disable arrives only with the next successful sync.

## Staff & Access

The screen lives under Register Administration → Staff & Access. It is visible to a session whose signed snapshot includes `users:read` for this store. Actions check the matching permission before they run.

The list shows staff code, name, branch, role, status, last local login, provisioning status, pending sync, and a permission summary.

Actions: Add Staff, Edit Staff, Assign Role, Reset PIN, Disable User, Enable User, View Permissions, View Audit History.

## Create while offline

1. The snapshot authorizes `users:create` for this store.
2. Active local users plus pending local users are below the seat cap in the entitlement.
3. The new user id is a UUID generated on the register.
4. Name and staff details are saved.
5. The PIN is hashed with Argon2 and a new salt. The PIN value is not retained.
6. The role's permissions are a subset of the actor's snapshot. `Super Admin` and any platform role are refused.
7. The user row, the audit row, and the outbox provisioning event commit in one SQLite transaction.
8. The account can unlock this register immediately.
9. The UI status is `LOCAL ACTIVE · PENDING SERVER PROVISIONING`.

The account is not shown as active for the company. Other registers do not receive it until the server accepts the event and those registers pull it. There is no shared-LAN user broadcast in this release.

Disable, enable, role change, and PIN reset follow the same transaction shape. A role change records actor, target, previous role, new role, previous permissions, new permissions, tenant, branch, terminal, device sequence, timestamp, and reason. The audit row is not updated later. The outbox event carries the change.

## Server acceptance and rejection

The provisioning handler runs in `sync_service` beside the existing user rules in `rbac_service`. It checks the seat cap with `assert_room`, duplicate identity, role, branch, actor authority, and tenant.

On accept, the user becomes a normal tenant user. Other registers learn about them on pull.

On reject, the register keeps the user row and the audit trail, stores the server reason, and disables local unlock or applies the reconciliation state the event result names. The UI shows that reason to the administrator. The event stays in the queue history. A rejection never leaves a broader permission set in force than the last accepted snapshot.

Rejection reasons include seat limit, duplicate user, invalid role, invalid branch, unauthorized administrator, tenant mismatch, and policy violation.

## Tests O5 must record

Disconnected register, cached Store Manager. Create a cashier, set a PIN, unlock locally, assign a permitted role, change a permission inside the snapshot, disable, enable, reset PIN. Attempts to create a tenant Super Admin, to reach platform administration, to edit another branch, and to pass the seat cap are refused on the register. After reconnect, accepted users exist on the server. A second register sees them only after pull. A forced server rejection disables the local account, shows the reason, and keeps the audit row.

O1 did not run these tests.
