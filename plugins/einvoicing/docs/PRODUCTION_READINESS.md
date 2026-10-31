# Production readiness

Status: not ready for a live UAE e-invoice submission.

Blocked on:

- Applying and rolling back `einvoicing_0001` on a copy of the tenant database.
- An accredited ASP sandbox, with that provider's documented authentication, payload, and webhook signature. The `mock` adapter must never be configured as production.
- PINT AE schema validation for profile `pint-ae-billing-1@ae-1` or a newer published profile.
- A console price for `uae_einvoicing` (the seeded row is 0 fils until an operator sets it).
- Nginx and PM2 entries on the server. They are documented beside the plugin and are not in the live ecosystem file.
- Confirmation of the ASP appointment date against Ministerial Resolution 66 of 2026. See `UAE_COMPLIANCE_SPECIFICATION.md`.

What is safe to ship behind the entitlement flag: the register still completes a sale when this plugin is absent, B2C receipts are unchanged, and a missing outbox table does not roll back the sale.
