# O8 business-profile offline test plan

Status: **NOT STARTED**. These cases are the O8 execution list. O8.1 did not run them. A laundry UI report, including `docs/laundry/LAUNDRY-ORDER-INTAKE-FINAL-ACCEPTANCE.md`, is not evidence for any row here.

Profiles come from `BusinessProfile` in `packages/shared-types/src/capabilities.ts`. Grocery is the supermarket profile. `wholesale_retail` is a second wholesale id and shares the electronics inventory tabs. There is no further implemented profile.

Shared rules for every profile:

- Product search, barcode, SKU, and variant selection show the same SQLite allocation remainder once the backlog item is integrated. Until that command exists, the allocation column below is **BLOCKED**.
- Price and tax come from the frozen `checkout_settings` document and the line's `tax_rate_bps`. A later policy change does not rewrite a queued sale.
- Customer search uses the existing customer cache. A sale without a customer still queues.
- Cash short of the total is refused. Card, QR, and pay-later queue only with a provider intent of `PAID`. No new offline approval is added.
- The queued sale and its allocation consumption commit in one SQLite transaction, then survive a process restart.
- A return queues only against a sale this register already has, and it does not increase the allocation remainder. The server return path is unchanged.
- Staff actions use the local outbox. A cashier without `pos:access` does not unlock. Five wrong PINs lock the local row.
- Native evidence is a verified acceptance window, or **NOT RUN**.

Pharmacy and laundry have extra gates that the other profiles do not.

## Matrix

| Profile | Id | Product data | Pricing and tax | Customer | Payments | Allocation | Persistence | Returns | Staff | Workflow that must stay specific | Native |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Grocery and supermarket | `grocery` | Catalogue, PLU, embedded weight barcode | Frozen rate on the line. Weight quantity in grams. | Cache lookup | Cash if covered. Card, QR, pay-later need `PAID`. | Remainder, not branch on-hand. 4.250 kg cannot become 4.251 kg. | Queue plus allocation, restart. | Cached sale only. | `pos:access`, lockout. | Department keys stay a grocery checkout control. | NOT RUN |
| Electronics and wholesale | `electronics_wholesale` | Catalogue plus serial cache | Frozen rate. Wholesale mode when the customer is wholesale. | Cache, including wholesale | Same tender rules. | A serial not on this terminal is not sold offline. `serials.rs` `taken` is this till's queue only. | Queue plus allocation. | Cached sale only. The serial is not offered again from this queue. | Same. | Serial selection is not a second ledger. | NOT RUN |
| Wholesale retail | `wholesale_retail` | Same as electronics | Same | Same | Same | Same | Same | Same | Same | Same tabs as electronics. Do not invent a third stock rule. | NOT RUN |
| Fashion and retail | `retail_fashion` | Model and variant attributes | Each variant keeps its own price. | Cache | Same tender rules. | Each variant has its own remainder. The grid must not sum them. | Queue plus allocation. | Cached sale only. | Same. | `VariantPicker` is the fashion path. | NOT RUN |
| Restaurant | `restaurant` | Catalogue and open-order cache | Frozen rate. Tip stays on the existing payload field. | Cache, optional | Same tender rules. | Allocation for stocked lines. A made-to-order line stays exempt. | One queue batch per send. | Cached sale only. | Same. | One kitchen ticket per send. Do not add a second ticket on retry. | NOT RUN |
| Cafe | `cafe` | Same food catalogue | Same | Same | Same | Same | Same | Same | Same | Same ticket rule as restaurant. | NOT RUN |
| Quick service | `quick_service` | Same food catalogue | Same | Same | Same | Same | Same | Same | Same | Same ticket rule. | NOT RUN |
| Pharmacy | `pharmacy` | Catalogue may download | Frozen rate is present and is not used for a medicine sale offline | Cache may load | No offline medicine tender of any kind | Allocation does not override the block | A blocked charge writes no queue row | Not offered offline for a medicine | Same unlock rules | `blockPharmacyOfflineSale` in `checkout.ts` stays. The message remains `PHARMACY_OFFLINE_SALE`. | NOT RUN |
| Laundry | `laundry` | Laundry services and garment types, not retail stock | Server prices the order when it is online. The register does not invent a tariff. | Existing customer sync | A deposit is the laundry deposit field, not a card provider. Express and a non-zero deposit are not queued offline. | Do not allocate garments as inventory. | A non-express, zero-deposit intake may use the existing local laundry queue. Production moves stay online. | Not a retail return. | Same unlock rules. Laundry does not gain a second staff system. | Sidebar stays Orders. `CheckoutPage` stays unmounted. | NOT RUN |

## Cases that apply to one profile only

Pharmacy, offline, any tender: `chargeGate` returns the medicine message and `enqueue_events` is not called. This is already covered by `checkout.pharmacy.test.ts` for the gate function. The native window is still **NOT RUN**.

Laundry, retail checkout: with profile `laundry`, the register opens Orders. Mounting `CheckoutPage` is a failure. An offline production scan, machine move, or packing change is a failure if it queues.

Electronics, same serial on two tills: the local cache may show it. The second offline sale is refused when the serial is not in this terminal's allocation. The server still rejects a duplicate serial at sync. The test uses two disposable registers.

Grocery, weight: a line of 4250 grams against a remainder of 21250 grams queues. 21251 grams does not queue and does not change the remainder.

Fashion: two sizes of one model with remainders 1 and 0. The grid can add the size with 1 and refuses the size with 0.

Restaurant: send once, kill the process, restore. The open order has one ticket id in the queue, not two.

## What is already tested, and what is not

| Area | Existing evidence | Missing |
| --- | --- | --- |
| Pharmacy offline block | `checkout.pharmacy.test.ts` | Native window |
| Entitlement gate | `checkout.entitlement.test.ts`, Rust verify tests | Release public key, native restart |
| Frozen tax | `checkout.snapshot.test.ts`, bootstrap pytest | Native window |
| Allocation library | `tests/test_allocations.py`, `allocation.rs` tests, `allocation.test.ts` | UI and `enqueue_events` |
| Staff library | `tests/test_staff_provision.py`, `staff.rs` tests, `staffAccess.test.ts` | Settings actions, command unlock, feed pull |
| Profile navigation | Laundry UI vitest for Orders versus Checkout | Offline laundry queue on a native window |
| Tenders | `tenders.ts` as read in the O4 matrix | The O4 cash and card cases were **NOT RUN** and stay **NOT RUN** until executed |

## Order

Run the shared allocation and staff cases after those commands exist. Run pharmacy and laundry next, because a regression there is a safety failure even when the retail profiles pass. Run native last, one acceptance identity at a time, using `O8-NATIVE-AND-RLS-TEST-PLAN.md`.
