# Tenant security

- Portal handlers call `active_tenant_id()`. They discard `tenant_id` from the body.
- List and get queries filter `Invoice.tenant_id`. A foreign invoice id returns 404.
- The standalone process reads `tid` from the API JWT and rejects a token without it or when `JWT_SECRET` is empty.
- Webhooks select `ProviderAccount` by provider code and participant id. The account's tenant is the only tenant written. A disagreeing body `tenant_id` is audited and rejected.
- Signatures use `hmac.compare_digest`. Timestamps older or newer than 300 seconds are rejected.
- Provider secrets are Fernet-sealed. Missing `EINVOICING_CREDENTIAL_KEY` raises before a seal. API responses do not include the ciphertext or the opened secret.
- RLS in the migration is the same `tenant_isolation` policy as the API. It applies only after the migration runs on PostgreSQL. SQLite tests enforce the filter in the query.
- Writes call `require_capability(Capability.UAE_EINVOICING)`. Reads of history remain for `portal:reports_read` when rows already exist. The portal route and the Compliance menu still hide the page when the capability is off, so expired tenants do not see the screen until the menu rule is relaxed. That gap is recorded in `PRODUCTION_READINESS.md`.
- The register never receives provider configuration.
