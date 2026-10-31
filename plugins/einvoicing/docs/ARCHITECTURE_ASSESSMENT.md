# Architecture assessment

Date of inspection: 31 October 2026. This describes the repository as it is. It is not a compliance certificate.

## 1. Existing tables to reuse

Operational data lives in the tenant database. Control-plane tenants live in the control database when `CONTROL_DATABASE_URL` is set, so plugin rows must not foreign-key `tenant_id` to `tenants`.

| Table | Use |
|---|---|
| `sales`, `sale_items` | Posted money in integer cents. `tax_cents`, `tax_rate_bps`, `subtotal_cents`, `total_cents` are the VAT snapshot. Do not recompute them. |
| `returns`, `return_items` | Refund amounts and `credit_note_number`. `original_sale_id` points at `sales`. |
| `customers` | `trn_vat_number`, `name`, `company_name`, `address`, `tax_treatment`. There is no government-buyer flag. |
| `stores` | Branch. `address`, `city`, `emirate`, `country`. |
| `business_settings` | `legal_name`, `trn`, `country`, `standard_rate_bps`, `tax_authority` (default `fta`), `purchased_capabilities`. |
| `users`, `devices` | Actors. POS sync authenticates with a device key, not a browser tenant id. |
| `e_invoices` | Existing ZATCA-shaped store. FTA's adapter sets `issues_einvoices = False`, so UAE sales do not get a row here. Leave this table to that adapter. |
| `subscriptions`, `subscription_items`, `billing_addons` | The only add-on catalogue. |
| `user_addon_access` | Per-user grant after a module is purchased. |
| `outbound_messages` | Customer messaging outbox. Not used for tax submissions. |
| `audit_logs` | Core audit. The plugin keeps its own `einvoicing_audit_logs`. |

## 2. Existing APIs to reuse

- `POST /api/v1/sync/push` records the sale (`sale_service.record_sale`) and the return (`sync_service.apply_sale_return`). Checkout does not call a separate invoice API.
- `GET /api/v1/exports/einvoices/{sale_id}.xml` builds PINT AE UBL on demand (`export_service.pint_ae_invoice`). CustomizationID in that exporter is `urn:peppol:pint:billing-1@ae-1`. That file is an export, not an ASP submission.
- `GET /api/v1/sales/{id}/invoice.pdf` and the credit-note PDF stay the human-readable tax documents.
- `GET /api/v1/einvoices` reads the ZATCA-shaped `e_invoices` table. It is not the UAE submission register.
- Billing catalogue and `module(Capability)` are the entitlement gate.

## 3. Existing services to integrate with

- Tenancy: `TenantContextMiddleware` resolves the store from `X-Tenant-Domain` or `Host`. JWT claim `tid` must match that store.
- VAT: `app.services.tax.line_tax` already rounded the line. `sales.tax_snapshot` freezes the branch tax profile.
- Tax authority: `FtaAdapter.issue()` returns `None`. The plugin must not turn that adapter into a live submitter.
- Jobs: APScheduler inside the API process, plus Redis for cache and rate limits. There is no Celery. The plugin worker is a separate loop over `einvoicing_outbox`.
- Add-ons: `Capability` in `apps/api/app/core/capabilities.py`, mirrored by `packages/shared-types/src/capabilities.ts`. `ensure_module_addons` inserts a `billing_addons` row with `monthly_fils = 0` until the console sets a price.

## 4. Add-on entitlement

New code `uae_einvoicing` ("UAE e-Invoicing") is optional for every current business profile and is not part of any starter preset. Purchase, grace, and expiry stay on `subscriptions` and `business_settings.purchased_capabilities`. Route writes call `require_capability`. Reads of existing invoices stay available to a reports user after the module is off, so history is not deleted with the entitlement. The menu itself follows the live capability.

## 5. Tenant isolation

Request sessions call `set_config('app.tenant_id', ...)`. RLS policy `tenant_isolation` is the pattern copied onto the new tables for PostgreSQL. The plugin never takes `tenant_id` from a JSON body. Portal routes use `active_tenant_id()`. The standalone process uses the JWT `tid` claim. Webhooks resolve the tenant from `einvoicing_provider_accounts.participant_id`.

## 6. Plugin-owned tables

`einvoicing_settings`, `einvoicing_provider_accounts`, `einvoicing_invoices`, `einvoicing_invoice_lines`, `einvoicing_submissions`, `einvoicing_submission_attempts`, `einvoicing_credit_notes`, `einvoicing_outbox`, `einvoicing_webhook_events`, `einvoicing_audit_logs`.

Tax breakdowns and status history are the invoice payload plus audit rows, not extra copies of `sale_items`. Provider secrets are columns on the account row, sealed with Fernet, and omitted from API responses. Alembic revision `einvoicing_0001` uses version table `alembic_version_einvoicing`. It has not been applied to the development or production database.

## 7. POS integration

`CheckoutPage` still prints the existing receipt and still completes when the API or the plugin is down (`ChargeOutcome` `queued`). If the add-on is on and the customer has `trn_vat_number`, the notice says the e-invoice is pending and that the receipt is not provider acceptance. The register does not hold ASP credentials and cannot set an accepted status. A buyer TRN causes `einvoicing_bridge.note_sale` after the sale is priced. No TRN means no outbox row.

## 8. Business Portal

`Compliance → e-Invoicing` at `/einvoicing`, gated by `uae_einvoicing` and `portal:reports_read`. The page reads `/api/v1/einvoicing/dashboard` and `/api/v1/einvoicing/invoices`, and it can run the mock connection test. It does not offer a download that the server cannot produce.

## 9. Company Console

No new billing engine. The next catalogue load inserts the add-on through `ensure_module_addons`. Prices stay 0 fils until an operator sets them in the existing Add-ons screen. Activation is the existing subscription item and `publish_purchased`.

## 10. Deployment

Production in this repo is PM2 (`deploy/ecosystem.config.cjs`) behind nginx, with host Redis. Docker Compose is local Postgres, Redis, and Ollama only. The plugin PM2 file is `plugins/einvoicing/deployment/ecosystem.einvoicing.cjs` and is not included in the live ecosystem, so a normal deploy does not start a process that the server does not have yet. Suggested bind is `127.0.0.1:8090`. The portal currently calls the API origin, and the API imports the plugin package, so one process can serve the portal while the worker runs separately.

## 11. Risks and missing information

- No accredited ASP contract, sandbox credentials, or provider API specification is in the repo. The only adapter is named `mock`.
- Official PINT AE XSD was not imported. `export_service.pint_ae_invoice` is the existing UBL export and was not re-validated against a schema file in this change.
- MD 244 of 2025 and the FTA notice of 25 October 2026 disagree on the AED 50 million ASP appointment date (31 July 2026 in the February 2026 guidelines, 30 October 2026 in the later FTA notice). The amendment text of Ministerial Resolution 66 of 2026 was not loaded into this workspace.
- There is no customer field for a government buyer. B2G is a list of customer ids on `einvoicing_settings`.
- Service charge and tips are not separate canonical lines. A sale whose line nets do not equal `subtotal_cents` fails validation instead of being invented into balance.
- The plugin migration has not been applied. Until it is, the outbox insert is inside a savepoint and a missing table does not roll back the sale.
- Official submission deadlines were not coded as a universal timer. The guidelines describe the ASP exchange; they do not give this product a single number of minutes.

## 12. Recommended sequence

1. Apply `einvoicing_0001` on a disposable database and confirm upgrade and downgrade.
2. Set the console price for `uae_einvoicing`.
3. Obtain one pre-approved ASP's sandbox pack and implement that adapter beside `mock`.
4. Validate generated UBL against the PINT AE package published for the selected profile version.
5. Only then point a tenant at `production` and an accredited account.
