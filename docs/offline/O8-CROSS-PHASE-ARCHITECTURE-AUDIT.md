# O8 cross-phase architecture audit

The offline register is one Tauri process with one SQLite file per terminal. The API remains the authority for accepted sales, stock movements, and staff that other terminals may use.

## Lifecycle

| Step | Where it lives |
| --- | --- |
| Activation | `apps/desktop/src-tauri/src/terminal.rs` `activate`. Server `apps/api/app/routers/v1/terminals.py`. |
| Device identity | `TerminalState.device_public_key`. DPAPI envelope in `terminal.rs`. |
| Permanent entitlement | `apps/api/app/services/entitlement_service.py` signs. `entitlement.rs` `code_for` verifies. Payload includes `limits.staff`. |
| Unlock | `auth.rs` `finish_offline`. Argon2, five attempts, `pos:access`. No access token. |
| Staff permissions | Cached `permissions` on `cached_users`. Server roles in `apps/api/app/core/permissions.py`. |
| Product bootstrap | `apps/api/app/services/bootstrap_service.py`. Local `bootstrap.rs`. Allowlist is products. |
| Incremental pull | Same bootstrap service. Cursor does not advance across a gap. |
| Checkout prices | `apps/desktop/src/features/checkout/cart.ts`. Snapshots stay on the queued sale. |
| Queue | SQLite `sync_queue`. Server `apps/api/app/services/sync_service.py`. Batch is all-or-nothing. |
| Conflicts | Same key and a different hash is `idempotency_conflict`. No force-sync. |
| Allocation | `allocation.rs` verifies the manifest. `db.rs` `consume_allocation` writes the queue in the same transaction. Server `allocation_service.py` reserves `quantity_reserved` and sales still call `move_stock`. |
| Staff provisioning | SQLite `staff_provisioning`. Server `staff_provisioning_events`. Not `sync_queue`. |
| Other terminals | `GET /api/v1/users/staff-feed` after acceptance. `staff.rs` `import_accepted`. |

## Gaps this phase closed

- Product search, barcode selection, and the product card now attach `allocation_remaining` from verified SQLite rows when the register is offline. The cart already refused a sale when that field was present. It no longer falls back to branch `stock_quantity` for those rows. A tampered manifest is omitted, so the product has no remainder and the cart blocks.
- Staff & Access submits create, edit, PIN reset, and disable through the signed-in session. The seat cap is read from the verified entitlement `limits.staff`. A missing or invalid document blocks creation.
- `verify_pin` accepts an Argon2 PHC string and still accepts the existing scrypt PIN. Ordinary user list responses do not include the verifier.
- Local provisioning rows record tenant id, originating terminal id, and schema version. The server event records `origin_terminal_id`, `schema_version`, and `base_version`. Tenant id on the server still comes from the tenant session, not from the body.

## Gaps left in place

- Native window acceptance was not run.
- PostgreSQL row-level security was not run with `ai_pos_app`.
- No authorized production entitlement public key was supplied. Release builds keep an empty trusted-key list unless `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY` are set at compile time. The test key is added only under `cfg(test)`.
- Lost-terminal stock write-off and financial conflict adjustment stay awaiting approval.
- `awaiting_review` is not a server status. A transport failure can be marked `retryable` locally without a new event id. A domain refusal stays `rejected`.
- Profile-specific workflows were not each clicked through on a register. The capability matrix says so.
