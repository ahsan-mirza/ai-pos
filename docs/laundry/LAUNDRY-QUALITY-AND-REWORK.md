# Laundry quality and rework

The inspector scans a garment and sees the order, service, intake condition, photos, and production history. The checklist covers cleaning, stain removal, finishing, ironing, fabric, buttons, zippers, the tag, the order, and special instructions.

Results:

| Result | Effect |
| --- | --- |
| `PASS` | Sets the QC result and closes the open rework task. |
| `FAIL` | Requires a reason. Moves the garment back to the required earlier stage and increments the rework count. |
| `REWORK_REQUIRED` | Same controlled return as a failure. |
| `MANAGER_REVIEW` | Holds the garment and does not move it. |

A failed inspection cannot go straight to ready. The inspection row is kept. Photos of a new problem are appended. Intake photos are not replaced.

Rework returns the garment only to a stage that exists on its workflow. Completing rework is allowed once the garment is back at quality check, and that completion requests a new inspection. Earlier inspections and events remain.
