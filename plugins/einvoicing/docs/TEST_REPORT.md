# Test report

Run on 31 October 2026. Disposable SQLite only. The AxizPOS development database was not migrated.

## Executed

`plugins/einvoicing/tests/test_plugin.py`

```
18 passed in 0.74s
```

Covers health, B2B/B2G/B2C classification, 15-digit TRN rejection, fils formatting, stable hashes, mock-only provider registry, accept, reject, retry eligibility, tenant separation, validation failure without a provider reference, line-total mismatch, B2C not loaded, outbox processed once, credit note amounts and idempotency, no credit note without an e-invoice, webhook signature, stale timestamp, replay, cross-tenant claim, secret absent from the connection response, and the five-attempt cap.

`apps/api/tests/test_capabilities.py` (catalog only):

```
test_python_and_typescript_catalogs_match — 1 passed
test_frontend_eligibility_matches_every_business_type — passed
test_optional_modules_are_the_compatible_ones_outside_the_preset — passed
test_every_preset_is_consistent — 7 passed
```

`uae_einvoicing` is optional for every current profile and is not in a starter preset.

## Not executed

The numbered plan from TEST-001 through TEST-150 was not all run. In particular:

- Migration upgrade and downgrade against PostgreSQL.
- Two live tenants through HTTP with RLS.
- Official schema validation.
- Any accredited ASP sandbox.
- Portal and POS browser passes. The signed-in store does not have the add-on, and the register locks after a reload.
- Performance numbers. No threshold is claimed.

A mock acceptance is not FTA acceptance. `provider_status` for that path is `MOCK_ACCEPTED`.
