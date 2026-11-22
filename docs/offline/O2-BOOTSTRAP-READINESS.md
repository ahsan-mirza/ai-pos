# Bootstrap readiness

`entitlement::readiness` returns the first matching state:

1. Damaged storage → `REQUIRES_ONLINE_RECOVERY`
2. Not activated → `NOT_ACTIVATED`
3. No entitlement → `ENTITLEMENT_MISSING`
4. Any other verification failure → `ENTITLEMENT_INVALID`
5. Entitlement valid, local database not assessed → `ENTITLEMENT_VALID`
6. SQLite or `sync_queue` unreadable → `BOOTSTRAP_REQUIRED`
7. No cached product, no cached staff, or no capability snapshot → `BOOTSTRAP_INCOMPLETE`
8. Pending queue rows, or the last server snapshot said the subscription is blocked → `ONLINE_SYNC_REQUIRED`
9. Otherwise → `OFFLINE_READY`

`ONLINE_SYNC_REQUIRED` is a diagnostic. It does not by itself close ordinary selling. Selling follows the verification code: `VALID_PERMANENT_ENTITLEMENT` ignores the 24-hour lease, `MISSING_ENTITLEMENT` on an already activated O1 file keeps that lease, and every other code blocks.

`OFFLINE_READY` means the single-terminal baseline: a verified permanent entitlement, a readable SQLite file, a readable `sync_queue`, at least one cached product, at least one cached staff row, a capability snapshot, an empty pending queue, and no server-reported subscription block.

It does not mean multi-terminal stock safety, local staff administration, incremental pull, conflict handling, or support for every business profile.

The register command is `bootstrap_readiness`. The status bar stores the code on `data-readiness` and adds it to the footer title. A missing command leaves the value `unchecked`.

Verification codes returned beside the readiness state are the O2 list: `VALID_PERMANENT_ENTITLEMENT`, `MISSING_ENTITLEMENT`, `INVALID_SIGNATURE`, `UNKNOWN_SIGNING_KEY`, `DEVICE_BINDING_MISMATCH`, `TENANT_BINDING_MISMATCH`, `BRANCH_BINDING_MISMATCH`, `TERMINAL_BINDING_MISMATCH`, `UNSUPPORTED_SCHEMA`, `STORAGE_DECRYPTION_FAILED`, and `MALFORMED_ENTITLEMENT`.
