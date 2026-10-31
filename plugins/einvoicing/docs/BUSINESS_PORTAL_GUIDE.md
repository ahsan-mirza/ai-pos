# Business Portal

Navigation: Compliance → e-Invoicing, route `/einvoicing`.

Visible when the tenant has `uae_einvoicing` and the user has `portal:reports_read`.

The page shows:

- Counts from `GET /api/v1/einvoicing/dashboard`: eligible, queued, accepted, rejected, validation failures, credit notes, and whether a provider account is connected.
- A banner that the connected provider is the mock, not an accredited ASP.
- A status filter and the invoice register from `GET /api/v1/einvoicing/invoices`.
- Retry on rows whose status is `REJECTED`, `RETRY_PENDING`, or `PROCESSING_ERROR`.
- A connection test that posts `provider_code: "mock"`.

Company legal name, TRN, address, and VAT rate stay on the existing store and tax settings. This page does not copy them.

Not built in this pass: a multi-step onboarding wizard, branch series editor, human-readable invoice download, structured XML viewer, and a dedicated audit-log screen. Audit rows are written to `einvoicing_audit_logs`. Configuration is available on the API (`GET` and `PUT /configuration`) and is not a separate wizard yet.
