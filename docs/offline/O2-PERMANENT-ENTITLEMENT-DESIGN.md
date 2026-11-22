# Permanent entitlement design

Implemented in this phase. O3–O8 are not part of this design.

## Algorithm

Ed25519. The API uses the `cryptography` package already in `apps/api/requirements.txt`. The register uses `ed25519-dalek` 2.

The API holds the seed in `ENTITLEMENT_SIGNING_SEED` (standard base64 of 32 bytes) and the id in `ENTITLEMENT_SIGNING_KEY_ID`. Both default to empty, which refuses issuance with HTTP 503 `entitlement_unconfigured` and does not consume the one-time activation key.

The desktop release build trusts only a public key compiled in with `POS_ENTITLEMENT_KEY_ID` and `POS_ENTITLEMENT_PUBLIC_KEY`. Those are unset, so a release build rejects every signature as `UNKNOWN_SIGNING_KEY` and does not store it. The test seed `7` repeated 32 times, key id `o2-test-1`, is trusted only when the crate is compiled for tests. It is not a production key and it is not in the release trust set.

## Payload

`entitlement_service.issue` signs the canonical JSON from `json.dumps(..., sort_keys=True, separators=(",", ":"))`. The register verifies those exact bytes, then requires the parsed JSON to canonicalize back to the same bytes.

Fields include `schema_version` 1, `entitlement_id`, `issuer` `axizpos`, `audience` `axizpos-register`, `tenant_id`, `branch_id` (the store id), `terminal_id` (the device id), `device_binding` (SHA-256 hex of the register's Ed25519 public key), `plan_id`, `issued_at`, `permanent: true`, and `key_id`.

`capabilities` is an empty list. The document is not a permission grant. `server_capabilities` is a snapshot of what the server had enabled and is not applied as new rights.

There is no expiry field. `issued_at` is an audit time. Verification accepts a `now` argument and does not use it. A payload that also contains `expires_at` still verifies if `permanent` is true.

## Issuance

`POST /api/v1/terminals/activate` is unchanged for a register that omits `device_public_key`. When that field is present, the same call signs the entitlement before the one-time key is marked used.

`POST /api/v1/terminals/entitlement` repeats issuance for an already activated register. A different device public key is rejected with 409 `device_binding` unless a new activation key is used (`rebind=True` on activate only).

The response carries `payload`, `signature`, and `key_id`. It does not carry the seed. Audit action `device.entitlement` records the entitlement id, key id, and thumbprint.

## What a disconnected register cannot know

A valid permanent entitlement does not mean the server still considers the subscription active. Remote suspension, plan changes, and permission revocation apply only after the register connects again.

## Stock

A valid entitlement does not allocate stock and does not change the inventory ledger. Ordinary selling uses the existing checkout checks and the existing `sync_queue`. When the entitlement verifies, a stale 24-hour lease does not close that path. Pharmacy medicine sales stay blocked while offline. A server-reported subscription block still closes selling. Per-terminal stock allocation is a later phase. `OFFLINE_READY` does not mean stock is partitioned between tills.
