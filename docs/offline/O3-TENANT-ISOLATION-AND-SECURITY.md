# Tenant isolation and security

Bootstrap and pull use `require_device`. The device row supplies the branch and the terminal. `active_tenant_id()` supplies the tenant. Pages and cursors are loaded with those three values. A second register in the same test tenant receives 404 for the first register's session and cannot pull with the first register's cursor.

A revoked device is rejected on the next request with 401 `device_revoked`, which is the existing device-token check.

The tests ran on the in-memory SQLite suite. They did not open PostgreSQL and they did not log in as the application database role. Row-level security was not re-proven. Application checks that did run:

- another register cannot read the session
- another register cannot use the cursor
- a tampered cursor is 401
- a cursor from the previous session is 409 `cursor_generation`
- a non-allowlisted dataset is 403
- a cursor past the retention floor is 409 `rebootstrap_required`
- an expired snapshot page is 409 `snapshot_expired`

The cursor MAC uses the server JWT secret. The entitlement signing seed is not used and is not returned. The cursor value stored on the register is not shown in the status bar.
