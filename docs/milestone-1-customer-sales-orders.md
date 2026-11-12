# Customer sales orders on restaurant and cafe profiles

This note is the entitlement proposal for Milestone 1. It does not change capabilities, checkout, kitchen, payment, or delivery.

## What is true today

`sales_orders` is a capability, not a profile. Code checks the capability. A profile is only the preset a business starts from.

- `wholesale_retail` includes `sales_orders` in its preset.
- `electronics_wholesale` does not include it in the preset. A business-wide administrator can switch it on, because it sits in the retail compatible set.
- `restaurant` and `cafe` presets do not include `sales_orders`. Their compatible set is the food set (`open_orders`, tables, kitchen, recipes, delivery channels, and the rest of that list). `sales_orders` is not in that set, so the business cannot turn it on from the portal.
- Routes under `/api/v1/sales-orders` require the `sales_orders` permission and the capability. A restaurant user is not granted that permission by the food preset.
- Restaurant and cafe orders stay on open orders: service type, kitchen send, channel webhooks, and the delivery trip. Those records are not sales orders.

Turning `sales_orders` on for every restaurant or cafe would also expose wholesale pricing, credit confirmation, pick lists, and backorders. That is the wholesale workflow and is not part of this proposal.

## Optional customer sales orders

Catering, corporate orders, bulk orders, and scheduled customer deliveries need a customer, a requested date, and a later delivery. They do not need tier prices, B2B credit, or a pick wave.

Proposed capability, separate from `sales_orders`:

| | |
| --- | --- |
| Key | `customer_orders` |
| Label | Customer orders |
| Available to | `restaurant`, `cafe`, and `quick_service`, as an optional module. Not part of those presets. |
| Not available as a substitute for | `sales_orders` on wholesale or electronics. Those businesses keep `sales_orders`. |
| Depends on | `open_orders` for restaurant and cafe, so the kitchen ticket still exists. No dependency on `wholesale_pricing` or `b2b_credit`. |

`compatible()` for food profiles would add only `customer_orders`. It would not add `sales_orders`, `wholesale_pricing`, or `b2b_credit`.

## Permission

New permission `customer_orders`, separate from `sales_orders`.

- A business-wide administrator can grant it to a portal role after the capability is on.
- A branch user sees only orders for that branch, the same store scope sales orders already use.
- A register device can create a customer order in the name of the cashier. It cannot change the capability or the reporting timezone.
- Kitchen, payment, and delivery permissions stay as they are. Confirming a customer order does not bypass `kds`, channel accept, or the delivery trip.

## What a customer order is allowed to do

- Record the customer, requested date, lines, and a note (catering, corporate, bulk, or a scheduled delivery).
- Keep the open-order ticket, kitchen send, and delivery status that restaurant checkout already uses.
- Show the order on the fulfillment board only when `customer_orders` is on. Counts still use the tenant reporting timezone, not a branch clock.

## What it must not do

- No wholesale price tiers, credit limits, or credit-override confirmation.
- No pick lists, bin waves, or backorder allocation.
- No change to channel webhook settlement, COD handover, or the rule that a delivery ticket closes only after the trip is delivered and the sale is paid.
- No second copy of the menu, modifiers, or KDS.

## Entitlement

`customer_orders` is off until a business-wide administrator switches it on, or IT support sets the managed override. A branch user cannot enable it. Purchased add-on rules stay as they are: if the module is later priced, an unpaid switch-on is refused the same way other paid modules are.

No code in this pass enables the capability or the permission.
