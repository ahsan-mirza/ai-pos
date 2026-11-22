# Offline security

Status: current controls only. Database encryption was not added and is not claimed.

- PIN material in SQLite is an Argon2 hash in `cached_users.pin_hash`.
- The device credential uses Windows CryptProtectData.
- The online bearer token is held in the Rust process, not in `localStorage`.
- The acceptance build refuses a developer data directory and a non-loopback API.
- Server RLS for the laundry proof uses `ai_pos_app` with `LOGIN`, `NOSUPERUSER`, and `NOBYPASSRLS`. That login was not rechecked in this phase.

Not done: encrypting the SQLite file, a signed entitlement, or a proof that secrets are absent from logs and exports. Customer PII, payment references, and queue payloads remain in the SQLite file as the current schema stores them.
