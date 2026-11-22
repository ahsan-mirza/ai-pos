# Laundry API

Prefix `/api/v1/laundry`. The router requires capability `laundry_operations`. Writes require `laundry:catalogue` or, for settings and templates, `laundry:configure`. Reads require portal access plus the capability.

| Method | Path | Permission | Result |
| --- | --- | --- | --- |
| GET | `/settings` | portal access | Current modes, tracking, precision, express capacity. |
| PUT | `/settings` | `laundry:configure` | Replaces those settings after validating modes and ranges. |
| POST | `/templates/{code}` | `laundry:configure` | Applies `laundry_shop`, `laundry_dry_cleaner`, `laundry_multi_branch`, or `laundry_commercial`. |
| GET, POST | `/categories` | read, or `laundry:catalogue` to add | Category code and name. |
| GET, POST | `/garments` | read, or `laundry:catalogue` to add | Garment type code and name. |
| GET, POST | `/services` | read, or `laundry:catalogue` to add | Service definition. |
| PATCH | `/services/{id}` | `laundry:catalogue` | Sets `is_active`. |
| GET, POST | `/price-lists` | read, or `laundry:catalogue` to add | Price list. A branch list must name a branch. A customer or corporate list must name a customer. |
| PUT | `/price-lists/{id}/rates` | `laundry:catalogue` | Sets one service rate. |
| POST | `/quotes` | portal access | Returns the priced line. A discount is accepted only when the caller has `pos:discount`. |

The quote does not persist an order. An accepted order stores the price and tax snapshots. Order intake is implemented and is described below.

Errors use the existing `{ "error": { "code", "message" } }` body. Codes include `invalid_unit`, `invalid_quantity`, `invalid_rate`, `discount_unauthorized`, `surcharge_unavailable`, `expired_price_list`, and `express_capacity`.

## Orders

Order routes live on the same router. They reuse customers, tax, deposits, and the existing tag identity. A garment is not a stock product.

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/orders` | Accept an order and persist price and tax snapshots. |
| GET | `/orders/{id}` | Order, garments, tags, deposits, and photos. |
| POST | `/orders/{id}/tags` | Issue or reprint a tag. A replaced tag stays on the garment history. |
| POST | `/orders/{id}/deposits` | Record a deposit on `laundry_deposits`. |

## Production

Production routes use the same `/api/v1/laundry` prefix and `laundry_operations` capability. The service validates the tenant, the branch, the workflow template, and the garment version. A scan never advances a stage. Repeating a scan at the same stage returns `already_scanned`.

| Method | Path | Permission | Result |
| --- | --- | --- | --- |
| GET | `/production/board` | view or a floor permission | Counts for the branch. |
| GET | `/production/shift` | view or a floor permission | Shift totals. |
| POST | `/production/scan` | view or a floor permission | Resolve a tag. Does not change the stage. |
| GET | `/production/garments/{id}` | view or a floor permission | Garment card, history, and `open_rework` when a rework task is open. |
| POST | `/production/garments/{id}/transition` | the stage permission, or override | Next stage only, unless override includes a reason. |
| GET, PUT | `/production/workflows` | view, or `laundry:configure` to save | Templates. Built-ins are `WASH_FOLD`, `DRY_CLEAN`, `WASH_IRON`, and `PRESS`. |
| GET, POST | `/production/categories` | view, or configure to add | Sorting category names. |
| GET, POST | `/production/batches` | view, or `laundry:batches:manage` | Open and create batches. |
| POST | `/production/batches/{id}/start` | batches | Start. |
| POST | `/production/batches/{id}/complete` | batches | Complete the batch. Garments stay at their own stages. |
| POST | `/production/batches/{id}/abort` | batches | Abort and clear the current batch on each item. |
| POST | `/production/batches/{id}/items` | batches | Add a garment or bag. A second open batch is `duplicate_batch`. |
| POST | `/production/batches/{id}/machine` | machines operate | Assign a compatible available machine. |
| GET, POST | `/production/machines` | view, or configure to register | Machine registry. |
| PATCH | `/production/machines/{id}` | configure | Status, including `MAINTENANCE`. |
| POST | `/production/machines/{id}/cycles` | machines operate | Start a cycle. The measured load is required when the machine has a capacity. |
| POST | `/production/cycles/{id}/complete` | machines operate | Complete the cycle and free the machine. |
| POST | `/production/cycles/{id}/fault` | machines operate | Fault. The machine becomes unavailable. |
| POST | `/production/inspections` | quality | `PASS`, `FAIL`, `REWORK_REQUIRED`, or `MANAGER_REVIEW`. |
| POST | `/production/rework/{id}/complete` | quality | Close rework only after the garment is back at quality check. |
| GET, POST | `/production/incidents` | view, or report to open | Open an incident. A blocking incident holds the garment. |
| POST | `/production/incidents/{id}/resolve` | resolve | Close the incident. No refund is posted. |
| POST | `/production/packing/scans` | packing | Reconcile one garment into its order. |
| POST | `/production/orders/{id}/packing/complete` | packing | Ready only when every required garment is packed, QC passed, and no hold remains. |

`READY_FOR_COLLECTION` is stored on the order. The garment row stores `READY`. Payment columns are not written by any of these routes.

Production error codes include `unknown_tag`, `replaced_tag`, `inactive_tag`, `wrong_branch`, `wrong_workflow`, `already_scanned`, `idempotency_conflict`, `duplicate_batch`, `machine_busy`, `over_capacity`, and `incident_hold`.

There is no `laundry_stage` sync entity. A push of that entity type returns 422. Machine assignment, batch membership, and stage changes stay disabled until the register is online.
