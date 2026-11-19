# Stage 3E.4 — Damaged-stock policy

This document records the current stock behaviour and the decision still required before any damaged-stock workflow is added. No option below is implemented by this stage. The existing `DAMAGED` status and the sale and release rules that reject it stay as they are.

## Existing implementation

`DAMAGED` is one of the stored lot statuses, next to `RELEASED`, `UNRELEASED`, `QUARANTINED`, `RECALLED`, and `SUPPLIER_RETURN`. The lot-event vocabulary also contains a `DAMAGED` action. Nothing in the inventory, waste, recall, quarantine, transfer, or supplier-return services writes that status or that action. The only assignments are in unit tests that construct a layer directly.

Sale and release already fail closed:

- A positive-quantity layer whose status is `DAMAGED` produces the sale reason `lot_damaged`.
- Release of a `DAMAGED` layer returns `lot_damaged` and does not change the layer.

Damage that staff can record today does not use that status. A manual stock adjustment with a damage reason (`DAMAGED_OR_EXPIRED`, `STOLEN_SHRINKAGE`, `SPOILAGE`, `QUALITY_REJECTION`) removes quantity. The movement type is `DAMAGE_SHRINKAGE`. Those reasons cannot add stock. Waste write-off from a batch line does the same: it decreases `quantity_remaining` and on-hand through the stock ledger, keeps the lot's previous status, and writes an adjustment audit row. Replaying the same adjustment id does not deduct again. A write-off larger than the layer is rejected, so the quantity cannot become negative through that path.

Serialized units use a different write-off status (`defective` or `quarantine` on the serial), not the pharmacy lot status `DAMAGED`.

## Current stock behaviour

| Question | What the code does today |
|---|---|
| Can a damaged unit stay in the saleable on-hand count? | Only if nobody records a removal. Recording damage through the existing adjustment or waste path removes the units. |
| Does the lot become `DAMAGED`? | No supported workflow sets that status. |
| Can a `DAMAGED` layer be sold or released if one existed? | No. Sale and release reject it. |
| Is the original manufacturer lot kept? | Yes. Waste and adjustments point at the existing batch line. |
| Is there a separate damaged-quantity balance? | No. Removed units leave available stock. They remain visible as ledger and audit rows, not as a saleable damaged pile. |

## Option comparison

### Option A — Quantity removal only

Damaged goods are recorded with the existing waste and damage adjustments. The affected quantity leaves available inventory. The lot status stays whatever it was (`RELEASED`, `UNRELEASED`, and so on) for any units still on the layer.

Advantages: the ledger, permissions, and batch drawer already exist. Damaged units are not left in the saleable quantity. No new lifecycle is required.

Open questions: whether staff need a screen that lists damaged units separately from the ledger; whether a removed unit's lot status should stay unchanged; whether pharmacy wants a reason that is distinct from general waste.

### Option B — Lot-level `DAMAGED` status

An authorized person marks the whole layer `DAMAGED`. Sale and release already refuse that status. The quantity still has to be removed, or it remains on hand but unsaleable.

Advantages: the lot is visibly unfit. A reviewer can see the status without reading the ledger.

Risks: a partly damaged pack would make the remaining good units unsaleable. Reversal would need its own authorization. The status would duplicate the quantity removal unless both are required together.

### Option C — Partial damage allocation

Record the damaged quantity against the existing manufacturer lot and leave the undamaged remainder on that lot. Eligibility of the remainder would follow the current release rules.

Advantages: partial damage stays traceable to the manufacturer lot. Good units can remain saleable when policy allows.

Risks: two quantities must move together under concurrency. Audit has to show who damaged which units. This is new accounting, not a status flag.

## Quantity accounting

Option A decreases on-hand and `quantity_remaining` once. Option B, by itself, does not decrease either; an unsold `DAMAGED` layer would still hold quantity that is merely unsaleable. Option C must decrease the saleable remainder by the damaged amount and store that amount somewhere other than the saleable balance. None of these may drive a quantity negative. The current waste path already rejects a quantity above the layer.

## Lot eligibility

A pharmacy sale may use a layer only when it is `RELEASED`, in date, and still has quantity. `DAMAGED` is not in that set. Option A leaves eligibility of the surviving units unchanged. Option B removes eligibility for every unit on the layer. Option C should leave the undamaged remainder eligible only when it still meets the release rules. Grocery FEFO is unchanged by this decision and must not start using the pharmacy status.

## Permissions

Waste and manual adjustments use the existing inventory permissions and store scope. Pharmacy release and quarantine stay with the authorized pharmacist and governance officers. Option B would need an explicit decision about who may mark a lot damaged and who may reverse it. Super Admin appointment rules are not a substitute for that decision. Option A does not add a permission.

## Audit

Option A already writes a stock-adjustment audit row and an immutable stock movement with the reason code and the user. Lot events stay append-only; Option A does not append a `DAMAGED` event because it does not change lot status. Option B would append a lot event and would need a reversal event. Option C would need both a quantity movement and a damage record that cannot be edited in place.

## UI

The waste and adjustment screens are the current place to record damage. The batch drawer does not offer "Mark damaged". Adding that button would be Option B or C and is out of scope until approved. Sale and release messages for a `DAMAGED` layer already exist and should remain.

## Database

No migration is required for Option A. `DAMAGED` is already allowed by the lot-status check. Option C would need a new quantity or child row and would have to preserve tenant row security. This stage does not add a table or change the check constraint.

## Risks

- Treating Option B as the whole-lot status would block good units in a partly damaged pack.
- Leaving damaged units on hand without a removal would keep them saleable whenever the lot is `RELEASED`. Option A is the path that prevents that.
- Building Option C without an approved quantity rule could double-count a removal or leave stock that the sale path still accepts.

## Recommended decision

Keep Option A as the operational policy. Record damaged and wasted units by removing that quantity through the existing adjustment and waste workflows. Do not add a control that sets `DAMAGED` on a layer. Leave the status in place so that, if a layer is ever stored as `DAMAGED`, sale and release continue to reject it.

Option B and Option C are not selected.

## Stage 3E.5 approval status

Option A is the recommended operational policy in this document. It is not an approved business decision. Stage 3E.5 does not implement it, does not change `DAMAGED`, and does not treat the existing adjustment and waste code as approval.

Approval status: **pending**. An authorized business decision is still required before any damaged-stock workflow is added.

## Decisions requiring explicit business approval

The following are not decided here and block any later implementation:

- Whether pharmacy needs a damaged-quantity history that is separate from the stock ledger.
- Whether a partly damaged manufacturer lot may keep its remaining good units saleable.
- Who may record damage, and whether that person must be different from the person who releases the lot.
- Whether a damage entry can be reversed, and by whom.
- Whether quarantined or recalled stock can also be written off as damaged, and which status wins.
- The regulatory quarantine and release policy named in Stage 3E.3, which this document does not replace.
