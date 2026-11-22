# Laundry production transitions

The API is the workflow engine. The register and Business Pro both call it. A garment follows the workflow copied from its service at intake. Changing that workflow is allowed only while the garment is `RECEIVED` or `TAGGED`.

## Templates

| Code | Stages |
| --- | --- |
| `WASH_FOLD` | RECEIVED, TAGGED, SORTING, WASHING, DRYING, FOLDING, QUALITY_CHECK, PACKING, READY_FOR_COLLECTION |
| `DRY_CLEAN` | RECEIVED, TAGGED, SORTING, PRE_TREATMENT, DRY_CLEANING, FINISHING, QUALITY_CHECK, PACKING, READY_FOR_COLLECTION |
| `WASH_IRON` | RECEIVED, TAGGED, SORTING, WASHING, DRYING, IRONING, QUALITY_CHECK, PACKING, READY_FOR_COLLECTION |
| `PRESS` | RECEIVED, TAGGED, IRONING, QUALITY_CHECK, PACKING, READY_FOR_COLLECTION |

A business can leave a mode disabled. The register hides stations the signed-in user cannot use. An already accepted garment still follows its own workflow code.

## Rules

- The next stage in the active template is the only ordinary move.
- `laundry:production:override` can move elsewhere when the reason is at least three characters. The event is still audited.
- A scan records the look-up and does not change the stage. A repeat scan during the same stage visit returns `already_scanned`.
- Unknown tags return 404. A replaced or inactive tag returns 409. A tag from another branch returns 403.
- Packing and ready require a `PASS` inspection when the template includes quality check, and they require no open hold.
- Ready also requires a packing scan for the current rework count.
- The garment stores `READY`. The order becomes `READY_FOR_COLLECTION` only when every garment is ready and none is held.
- Sending a ready garment back for rework returns the order to `IN_PRODUCTION`.
- Payment totals, deposits, and price snapshots are not updated by a transition.
- Each write claims `garment.version`. A stale version returns a conflict. The same idempotency key returns the existing event. A reused key with a different target returns `idempotency_conflict`.

`IN_PRODUCTION` remains the coarse status written by the older start-production action. The floor does not use that status. A garment left there is rejected as the wrong workflow.
