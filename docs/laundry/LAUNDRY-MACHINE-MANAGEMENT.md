# Laundry machine management

Business Pro registers machines. The register starts and completes cycles.

## Registry

A machine has an id, code, name, type, branch, capacity, capacity unit, supported cycles, and status.

Types: `WASHER`, `DRYER`, `DRY_CLEANING`, `PRESS`, `FOLDER`, `OTHER`.

Statuses: `AVAILABLE`, `RUNNING`, `MAINTENANCE`, `OUT_OF_SERVICE`, `DISABLED`.

Compatibility:

| Type | Workflows |
| --- | --- |
| Washer, dryer | Wash and fold, wash and iron |
| Dry-cleaning machine | Dry clean |
| Press | Press, wash and iron, dry clean |
| Folder | Wash and fold |
| Other | Any configured workflow |

## Cycle rules

- A new cycle is accepted only while the machine is `AVAILABLE`.
- Starting the cycle is a conditional update from `AVAILABLE` to `RUNNING`. A second start returns `machine_busy`.
- If a capacity is set, the operator must send the measured load weight. A weight above capacity returns 422. The server does not invent a weight.
- A fault marks the machine unavailable. The batch can be assigned to another compatible machine. Garments keep their own order and tag.
- A machine in maintenance or out of service cannot take a new assignment. The register reads that status from the API.
- Completing a cycle frees the machine. It does not mark the order ready.
