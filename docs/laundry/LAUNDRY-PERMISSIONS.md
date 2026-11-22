# Laundry permissions

Names follow the existing short permission style.

| Permission | Who needs it | What it allows |
| --- | --- | --- |
| `laundry:configure` | Business administrator | Operating modes, tracking, express capacity, and configuration templates. |
| `laundry:catalogue` | Catalog administrator | Categories, garment types, services, price lists, and rates. |
| `pos:discount` | Existing discount permission | A discount on a laundry quote. Catalog permission alone does not discount a quote. |

Production permissions, added in Phase 3:

| Permission | Station | What it allows |
| --- | --- | --- |
| `laundry:production:view` | Any signed-in floor user who may look | Production board, garment history, and shift summary. |
| `laundry:production:sort` | Sorting | Move a garment into sorting and assign a configured category. |
| `laundry:production:process` | Washing and dry cleaning | Washing, drying, pre-treatment, and dry cleaning. |
| `laundry:production:finish` | Finishing | Folding, ironing, and finishing. |
| `laundry:production:override` | Supervisor | A non-adjacent move, only with a reason of at least three characters. The audit row is still written. |
| `laundry:quality:inspect` | Quality | Pass, fail, rework, or manager review. |
| `laundry:packing:operate` | Packing | Packing scans and the ready-for-collection move. |
| `laundry:incidents:report` | Any operator | Open a missing, damaged, or process incident. |
| `laundry:incidents:resolve` | Supervisor | Resolve an incident. Resolution does not create a refund. |
| `laundry:machines:operate` | Machine operator | Start and complete a cycle, and report a fault. |
| `laundry:machines:configure` | Business Pro | Register a machine and change its status. |
| `laundry:batches:manage` | Batch lead | Create, start, complete, and abort a batch. |

Super Admin receives every laundry permission through the existing rule that the role holds every permission except `pharmacy:authorize_pharmacist`. No new global system role was added. Cashier and Store Manager do not receive these production permissions. The register shows a station only when the signed-in user holds the matching permission.

The portal page `/laundry` requires `laundry:catalogue` and the `laundry_operations` capability. The capability is off until the business profile or module settings include it.
