# Laundry architecture audit

Phase 0 record. The laundry module is a business profile on the existing AxizPOS services. It does not add a second database, customer book, payment ledger, tax engine, or inventory ledger.

## What already exists and must be reused

| Need | Existing place | Laundry use |
| --- | --- | --- |
| API | FastAPI `apps/api`, routers under `/api/v1` | Laundry catalog is `/api/v1/laundry`. Later order and production routes stay on this API. |
| Register | Tauri 2, Rust, React in `apps/desktop` | No laundry workspace in this phase. Counter intake will call the same API. |
| Business Pro | React portal in `apps/web` | Catalog page at `/laundry`, gated by the laundry capability and `laundry:catalogue`. |
| Tenant data | One PostgreSQL database per tenant, `tenant_id` on operational rows | New laundry rows use `TenantScoped`. Tests use the default tenant. |
| Isolation | Row level security and `ai_pos_app` (`20261119_0119`) | Migration `20261121_0121` enables and forces RLS on each new laundry table with `app_owner_may_bypass`. |
| Business type | `capabilities.ts` and `app/core/capabilities.py` | Profile `laundry`, capability `laundry_operations`. |
| Customers | `customers` and the CRM routes | Price lists point at an existing customer. No second customer table. |
| Tax | `app/services/tax.py` `line_tax` and branch or business tax policy | Quotes pass the configured rate. No rate is hardcoded. |
| Money | Integer cents and `div_half_up` | Piece, bag, and measured-unit quotes use that rounding. |
| Payments, invoices, shifts, stock | Existing sales, tender, invoice, shift, and inventory ledgers | Not called in this phase. Consumables later must post through the inventory ledger. |
| Permissions | `Permission` enum and system roles | `laundry:configure` and `laundry:catalogue`. Super Admin receives them because it holds every permission except the governed pharmacist appointment. |
| Audit | `audit.record` | Settings, catalog, price, and template changes are queued until commit. |
| Offline sync | Existing register queue | Not extended in this phase. |

## What this phase adds

- Profile `laundry` in the services group, with signup models for a small shop, a dry cleaner, a multi-branch laundry, and a commercial laundry. All four start with the same modules. Operating modes are settings, not extra capabilities.
- Catalog tables: settings, service categories, garment types, services, service-to-garment links, price lists, price rates, and workflow templates.
- A quote function. Measured units (kilogram, metre, square metre, hour) send an integer in the service precision. A precision of 3 and a quantity of 1250 is 1.250. Count units use a whole quantity.
- The quote applies the minimum charge, extras, and only the surcharges the service offers, then an authorized discount, then `line_tax`.
- A branch list is refused for another branch. A customer or corporate list is refused for another customer. A list outside its dates is refused. Express is refused when daily capacity is configured as zero. A null capacity means the limit is not configured.

## What is not built

Orders, garments in process, tags, photos, production stages, batches, machines, quality checks, claims, collection, pickup, delivery, packages, corporate linen, consumable consumption, reports, and offline intake are not in this change. Workflow templates store stage names only. They do not move an order.

Garments being cleaned are not stock. These tables do not change on-hand quantities.

## Migration

`20261121_0121` revises `20261119_0120`. It is additive. It has not been applied to the developer database, the inventory acceptance database, or production.
