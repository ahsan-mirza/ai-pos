# Stage 3F — Damaged-stock decision

## Approval state

No approval record was found in the repository or in Stage 3E.4 / 3E.5 / 3E.6 evidence. The existing adjustment and waste code is not an approval.

Approval state: **PENDING**. Stage 3F.1 did not add a damage workflow and did not treat the existing adjustment code as approval.

Implementation state: **not started**. No action was added that sets a layer to `DAMAGED`. Quantity accounting was not changed.

## Recommendation

Option A, unchanged from `docs/pharmacy/STAGE-3E.4-DAMAGED-STOCK-POLICY.md`.

Record damaged or wasted units by removing the affected quantity through the existing waste and damage adjustment workflows. The lot status of any units that remain stays as it was.

## What the code does today

| Item | Behaviour |
|---|---|
| Stored status | `DAMAGED` is allowed on `batch_items`, next to `RELEASED`, `UNRELEASED`, `QUARANTINED`, `RECALLED`, and `SUPPLIER_RETURN`. |
| Who writes `DAMAGED` | No inventory, waste, recall, quarantine, transfer, or supplier-return service. Tests may construct a layer directly. |
| Sale | A positive `DAMAGED` layer is rejected with `lot_damaged`. |
| Release | A `DAMAGED` layer is rejected with `lot_damaged` and is not changed. |
| Quantity removal | A damage reason (`DAMAGED_OR_EXPIRED`, `STOLEN_SHRINKAGE`, `SPOILAGE`, `QUALITY_REJECTION`) posts `DAMAGE_SHRINKAGE` and decreases quantity. Waste write-off does the same and keeps the previous lot status. |
| Negative quantity | A write-off larger than the layer is rejected. Replaying the same adjustment id does not deduct again. |
| History | The stock movement and the adjustment audit row are the history. Option A does not append a `DAMAGED` lot event. |
| Permissions | Existing inventory adjustment permissions and store scope. Pharmacy release and quarantine stay with the authorized pharmacist and governance officers. |
| Partial damage | Removing a quantity leaves the rest of the layer on its current status. That is Option A. It is not a new partial-damage ledger. |
| Recall or quarantine | Those statuses are unchanged by a damage adjustment. Whether a quarantined or recalled layer may also be written off is not decided. |
| Reversal | Not approved. Do not add a reversal of a damage entry until a named approver decides who may reverse it. |

## Required business approver

An authorized pharmacy operations owner, together with whoever the business names for stock-policy sign-off. Software testing does not fill that role.

## Still requiring a decision

- Whether pharmacy needs a damaged-quantity history separate from the stock ledger.
- Whether a partly damaged manufacturer lot may keep its remaining good units saleable.
- Who may record damage, and whether that person must be different from the person who releases the lot.
- Whether a damage entry can be reversed, and by whom.
- Whether quarantined or recalled stock can also be written off, and which status wins.
