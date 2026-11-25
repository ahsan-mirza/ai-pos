# Restaurant takeaway, delivery, and offline closure

Date: 25-11-2026

Continues `RESTAURANT-CAFE-RECIPE-CHECKOUT-OFFLINE-ACCEPTANCE.md` on the same disposable restaurant database. The register process `48928` had exited. The same executable was started again. The database, tenant, cashier, and API were not recreated.

## Environment

| Item | Value |
|---|---|
| Identifier | `com.axizpos.restaurant.portion` |
| Executable | `apps/desktop/src-tauri/target/portion-restaurant/ai-pos-desktop.exe` |
| SHA-256 | `874E37D84516FD3EC026DE355C5B8410CF28690521B94AFD108A70A0C813C71B` |
| Process after relaunch | PID 49056, HWND 13175578 |
| API | `http://127.0.0.1:18094`, health `{"status":"ok"}`, listener PID 10336 |
| Database | `%TEMP%\axiz-portion\restaurant\axizpos_portion_restaurant.sqlite` |
| Local register data | `%APPDATA%\com.axizpos.restaurant.portion` |
| Schema | `create_all`. Alembic `20261122_0135` was not applied. |
| Laundry till | Not running. It was not started. |

The path `target/zoom-shared/debug/ai-pos-desktop.exe` is a different binary (`793183653205CC8D38532DA3E323334A7497DDBC2F9FF54501D3B13AB3537502`). It was not used.

## Workstreams

| Workstream | Status |
|---|---|
| Restaurant takeaway | PASSED WITH LIMITATIONS |
| Restaurant delivery | PASSED WITH LIMITATIONS |
| Restaurant restart | PASSED WITH LIMITATIONS |
| Prepared-item offline replay | NOT RUN |
| Recipe-managed offline replay | NOT RUN |
| Cafe native startup | NOT RUN |
| Cafe portion pricing | NOT RUN |
| Cafe recipe behavior | NOT RUN |
| Cross-tenant isolation | NOT RUN |

The combined Restaurant/Cafe workflow stays **IN PROGRESS**.

## Takeaway — PASSED WITH LIMITATIONS

Order `20c4ecb1-1bfb-417f-9908-1c9feb42f604`, number 2, service `TAKEAWAY`, status `OPEN`, revision 2. Local tag `TW1`. Guest Portion Guest, phone `0501112233`. No second takeaway was created.

Sent lines:

| Line | Product | Portion | Unit | Qty | skip_recipe |
|---|---|---|---:|---:|---:|
| `19c23a16-7ee0-4d91-a833-e401734546b2` | Mineral Water | none | 200 | 1 | 1 |
| `53798796-f0c7-41ed-b889-32c4beabec08` | Chicken Karahi | Half `6ac101e5-323f-4cfc-9ae1-b1372b6f3c38` | 600 | 1 | 0 |

The orders screen after restart shows Portion Guest, AED 8.00, two lines, kitchen order placed. The open ticket shows Mineral Water at AED 2.00 and Chicken Karahi at AED 6.00, both sent to the kitchen, open to pay. The ticket was not settled. Sale tenders stayed at the earlier cash sales plus the restart sale below. Sending the round did not add a stock movement.

The orders panel shows the unit price and does not show the portion name Half. The server line stores `price_option_name` Half and `price_option_cents` 600. The server order row has no `customer_id`.

## Delivery — PASSED WITH LIMITATIONS

Order `c49bc0fc-bf6a-4b01-8ce8-aaca502032bd`, number 3, service `DELIVERY`, status `OPEN`, revision 2. This is a separate order from the takeaway. Guest Portion Rider. Local phone `0502223344`. Local address `12 Acceptance Road`.

Sent lines:

| Line | Product | Portion | Unit | Qty | skip_recipe |
|---|---|---|---:|---:|---:|
| `793fc993-fbc9-4350-b7d1-d9d4d4584f66` | Daal Channa | Small Plate `497ee798-77ad-448e-83ec-795c1f95b80c` | 300 | 1 | 1 |
| `b3754b66-0811-4d47-85e5-08005b930e15` | Mineral Water | none | 200 | 1 | 1 |
| `48d49003-5663-4940-bb50-5148a8b70bff` | Chicken Karahi | Half `6ac101e5-323f-4cfc-9ae1-b1372b6f3c38` | 600 | 1 | 0 |

The orders screen shows Portion Rider, AED 11.00, three lines, kitchen order placed, delivery pending, payment unpaid. The open ticket lists Daal Channa AED 3.00, Mineral Water AED 2.00, and Chicken Karahi AED 6.00, each sent to the kitchen. Checkout was not used. No new stock movement was created for the draft or the sent round.

The server columns `delivery_phone`, `delivery_address`, and `customer_id` are empty. The address and phone remain on the local ticket. The orders panel does not show the portion names. The server lines do.

## Restart — PASSED WITH LIMITATIONS

Before the relaunch the API was healthy and the three open orders, two completed sales, and three stock movements were already stored. After PID 49056 started, Portion Owner was signed in, the catalogue showed Chicken Karahi `From AED 6.00`, Daal Channa `From AED 3.00`, and Mineral Water AED 2.00, and Orders & Tables showed T-01 at AED 14.00 plus the takeaway and delivery tabs.

During that startup the register also recorded cash sale `PORTIONR-PR1-000003` at 2026-11-25 12:52:48: one Chicken Karahi Half, 600 cents, tax 30, total 630, `skip_recipe` 0. `recipe_usages` needed 2 and drew 0. Audit `recipe.stock_short` records short 2 for Channa. No fourth stock movement was created. On hand stayed 0. The sale did not settle T1, the takeaway, or the delivery. Opening movement `8c09f21ceaeb4942a87042723b59c8e5` is unchanged.

## Inventory

| Movement | Type | Quantity | After |
|---|---|---:|---:|
| `8c09f21ceaeb4942a87042723b59c8e5` | `AUDIT_ADJUSTMENT` opening | 100 | 100 |
| `c5f0e4193d87441381304d22ff4c7442` | `RECIPE_OUT` sale 000001 | -2 | 98 |
| `591432493cc8493bbd22a58bd0d9de19` | `RECIPE_OUT` sale 000002 | -98 | 0 |

On hand 0, reserved 0. Prepared lines on T1, takeaway, and delivery did not add movements. The shortfall on sale 000002 was not duplicated as a movement. Sale 000003 recorded a second shortfall audit and drew nothing.

Open orders have no payment arrangement and no tender of their own. Sale tenders are 3, matching the three cash sales.

## Offline — NOT RUN

The disposable API was left running so the reopened tickets could be read. No offline order was created and no replay was attempted.

## Cafe — NOT RUN

The cafe executable is `apps/desktop/src-tauri/target/portion-cafe-build/debug/ai-pos-desktop.exe`, SHA-256 `67990A3A24C8D6D57AFFA4A04BC77D7E2010125C60B7BC2782CA1A639D1C70B2`, identity `com.axizpos.cafe.portion`, API port 18095. It was not started.

A separate file `%TEMP%\axiz-portion\cafe\axizpos_portion_cafe.sqlite` already exists. It has users `portionowner` and `portioncashier`, ingredient Channa, and pre-packaged Mineral Water at 200 plus Daal Channa at 300 with Small, Medium, and Full Plate options. It has no open orders. That file was not copied from the restaurant database and was not used as native acceptance.

## Automated checks

`node scripts/python.mjs -m pytest tests/test_menu_recipe_mode.py tests/test_recipes.py tests/test_menu.py -q`

9 passed in 10.81s, exit 0.

No desktop or Rust files changed in this pass. `tsc` and `cargo check` were not rerun.

## Screenshot

`docs/restaurant/evidence/native/delivery-portion-rider.webp`

## Next phase

Disconnect only the restaurant API on port 18094, create an offline prepared-item order, replay it once, and confirm no duplicate ingredient movement. Then launch the cafe executable against its own database and walk portion selection, prepared-item mode, and one saved order. Do not deploy.
