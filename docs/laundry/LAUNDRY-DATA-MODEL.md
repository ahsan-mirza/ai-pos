# Laundry data model

Phase 1 tables. All are tenant scoped. Price lists may also name one existing branch or one existing customer.

| Table | Purpose |
| --- | --- |
| `laundry_settings` | One row per tenant. Operating modes, tracking mode (`individual`, `bag`, or `bulk`), weight precision, optional express daily capacity. |
| `laundry_service_categories` | Tenant-defined categories. Unique code per tenant. |
| `laundry_garment_types` | Tenant-defined garment types. Unique code per tenant. |
| `laundry_services` | Code, name, unit, base rate, minimum charge, minimum quantity, precision, optional surcharges, tax category, turnaround, workflow code, active flag. |
| `laundry_service_garments` | Which garment types a service applies to. |
| `laundry_price_lists` | Kind is `standard`, `premium`, `express`, `branch`, `customer`, or `corporate`. Branch and customer lists store the matching foreign key. `valid_from` and `valid_to` are optional dates. |
| `laundry_price_rates` | One unit price per service on a list. |
| `laundry_workflow_templates` | Ordered stage names. This is configuration only. |

There is no laundry order, tag, claim, package, or stock table in this phase. Inventory quantities are not columns on these tables.

Migration `20261121_0121` creates the tables and, on PostgreSQL, enables and forces row level security with the same tenant predicate as `user_preferences`.
