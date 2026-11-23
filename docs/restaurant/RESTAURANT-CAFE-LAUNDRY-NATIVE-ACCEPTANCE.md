# Restaurant evidence closure, Cafe, and Laundry

Date: 23-11-2026

Overall: **PASSED WITH LIMITATIONS**

No sale was settled. The installed register was not opened. The live laundry register was not opened. Grocery, electronics, and fashion were not launched again and their earlier limited results were not promoted.

| Workstream | Result |
| --- | --- |
| Restaurant Z1 order line | PASSED WITH LIMITATIONS |
| Restaurant Grilled Chicken edit | PASSED WITH LIMITATIONS |
| Cafe quantity and portions | PASSED WITH LIMITATIONS |
| Laundry disposable window | BLOCKED |
| Grocery | PASSED WITH LIMITATIONS, not re-run |
| Electronics | PASSED WITH LIMITATIONS, not re-run |
| Fashion | PASSED WITH LIMITATIONS, not re-run |
| Physical touchscreen | NOT RUN |

## Restaurant evidence closure

The previous process 44192 was not running. The disposable API replaces its SQLite file on start, so the Z1 line and the chicken line were created again and then inspected.

The 1000×1200 capture `docs/restaurant/quantity-modal-evidence/restaurant-z1-medium-plate-order-line.png` shows Table Z1, Occupied, Kitchen: New, Daal Channa · Medium Plate, 2 × AED 5.00, and line status New. The saved order is OPEN, quantity 2, unit 500 cents, portion Medium Plate, unpaid.

`restaurant-grilled-chicken-edit-restored.png` shows Breakfast selected and Extra cheese selected. The dialog text in the same moment includes unit AED 9.50 and Update item AED 19.00. Those amounts are below the visible frame. Cancel left the cart at 2 × AED 9.50, line AED 19.00, Breakfast, Extra cheese.

Identity for the window that produced these screenshots: `com.axizpos.restaurant.zoom`, PID 9696, HWND 3802388, SHA-256 `793183653205cc8d38532da3e323334a7497ddbc2f9ff54501d3b13ab3537502`, API `http://127.0.0.1:18093`.

## Cafe acceptance

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.cafe.portion` |
| Title | AxizPOS Cafe Portion |
| SHA-256 | `67990a3a24c8d6d57affa4a04bc77d7e2010125c60b7bc2782ca1a639d1c70b2` |
| PID | 38612 |
| HWND | 6754838 |
| API | `http://127.0.0.1:18095` |
| Database | `%TEMP%\axiz-portion\cafe\axizpos_portion_cafe.sqlite` |
| Store | `portionc` |
| Profile | cafe |
| Currency | AED |

Daal Channa was not preselected. Small Plate quantity 2 was AED 6.00. Medium Plate kept quantity 2 at AED 10.00. Full Plate quantity 3 was AED 27.00. The cart held those two portions as separate lines. Mineral Water had no portion section, minus stayed at 1, and a double add left one line at 1 × AED 2.00.

The Cafe capability preset does not include tables, so no dining floor was created. No modifier group was configured, and no recipe sale was walked. Those two checks are NOT RUN.

Screenshots: `docs/restaurant/evidence/cafe/`.

## Laundry acceptance

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.laundry.acceptance` |
| Title | AxizPOS Laundry Acceptance |
| SHA-256 | `cc0f6e8ed329f044496360cff91279465882c573e3f2b450c50a1652c59f2ac9` |
| PID | 57888 |
| HWND | 460040 |
| Data directory | `%APPDATA%\com.axizpos.laundry.acceptance` |
| API | `http://127.0.0.1:18082` |
| Database | `acceptance/laundry/pgdata` on `127.0.0.1:55821` |

The window opened on Unlock register for Laundry Tenant A, Branch A. Unlock stayed on Checking, so New Order was not reached. No laundry order was created. The garment quantity field, which is a labelled input and not the restaurant portion dialog, was not exercised.

Screenshot: `docs/restaurant/evidence/laundry/laundry-unlock.png`.

## Other profiles and touch

Grocery, electronics, and fashion keep the earlier limited results in `docs/ui-ux/POS-QUANTITY-PORTION-CROSS-PROFILE-ACCEPTANCE.md`. They were not opened in this pass.

Windows reports a touch pad and two pen devices. It does not report a touch digitizer. Physical touchscreen acceptance is NOT RUN.

## Automated tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/quantityModal.test.tsx src/features/checkout/priceOptionModal.test.tsx src/features/checkout/cart.test.ts --reporter=dot`

3 files, 31 tests, 0 failed, exit 0.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

## Next gap

Finish the disposable laundry unlock and exercise the garment quantity field on that same acceptance window. Then walk a Cafe modifier and a Cafe recipe on the disposable Cafe database. Physical touch still needs a digitizer.
