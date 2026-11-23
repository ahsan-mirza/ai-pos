# Quantity and portion dialog across business profiles

Date: 23-11-2026

Overall: **PASSED WITH LIMITATIONS**

Restaurant evidence is in `docs/restaurant/RESTAURANT-UNIFIED-QUANTITY-PORTION-MODAL-ACCEPTANCE.md`. This file records the other profiles on their own windows. A restaurant result is not used as a result for another profile.

No sale was settled. The installed register and the live laundry register were not opened.

## Cross-profile acceptance

| Profile | Quantity | Variants/options | Cart | Existing workflow |
| --- | --- | --- | --- | --- |
| Restaurant | PASS | Portion selection PASS | Two portion lines stayed separate. See the restaurant report. | Dine-in, takeaway, and delivery drafts saved unpaid |
| Cafe | PASS | Portion dialog. No portion was preselected. Small 2 is AED 6.00, Medium 2 stays AED 10.00, Full 3 is AED 27.00 | Full Plate qty 3 and Small Plate qty 1 stayed separate. Mineral Water stayed one line after a double add | Tables are not in the Cafe preset. Modifier and recipe walks were not run |
| Grocery | PASS | No portion section on Zoom Rice 1kg | Not exercised | Weighed scale dialog NOT RUN |
| Electronics | PASS | USB Cable uses the quantity dialog and no portion section | Not exercised | Serialized Handset opens the IMEI/serial picker |
| Fashion | PASS | Size and colour grid. No portion section and no portion labels | Not exercised | Variant stock and prices remain on the size/colour grid |
| Laundry | BLOCKED | BLOCKED | BLOCKED | BLOCKED |

## Grocery

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.grocery.zoom` |
| Title | AxizPOS Grocery Zoom |
| API | `http://127.0.0.1:18090` |
| Database | `%TEMP%\axiz-zoom\grocery\axizpos_zoom_grocery.sqlite` |
| Data directory | `%APPDATA%\com.axizpos.grocery.zoom` |
| PID | 35032 |
| HWND | 2495214 |

Zoom Rice 1kg opened “How many are you selling?” with the quantity stepper, unit price $10.00, quantity 1, and Add 1 — $10.00. The dialog did not contain “Portion size”. The process was closed without adding the line.

The disposable grocery catalogue has no weighed product, so the scale dialog was not opened. That check is NOT RUN.

Screenshot: `docs/ui-ux/quantity-profile-evidence/grocery-zoom.png`.

## Electronics

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.electronics.zoom` |
| Title | AxizPOS Electronics Zoom |
| API | `http://127.0.0.1:18091` |
| Database | `%TEMP%\axiz-zoom\electronics\axizpos_zoom_electronics.sqlite` |
| Data directory | `%APPDATA%\com.axizpos.electronics.zoom` |
| PID | 3200 |
| HWND | 14685398 |

Zoom USB Cable opened the same quantity dialog, unit price $15.00, with no portion section.

Zoom Serialized Handset opened “Select IMEI / serial”. The register reported no free cached units. The dialog has Cancel and Add to sale. It did not show a portion section. The line was not added.

`docs/ui-ux/quantity-profile-evidence/electronics-zoom.png` is the serial picker. The cable dialog text is in `profiles.json`; that capture was replaced by the serial screenshot.

## Fashion

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.fashion.zoom` |
| Title | AxizPOS Fashion Zoom |
| Executable SHA-256 | `6d54d2e5b0c6784e1ed0aec9a8690552b18a934759f1145802382f904af50859` |
| Size | 31,633,920 bytes |
| API | `http://127.0.0.1:18092` |
| Database | `%TEMP%\axiz-zoom\fashion\axizpos_zoom_fashion.sqlite` |
| Data directory | `%APPDATA%\com.axizpos.fashion.zoom` |
| PID | 56560 |
| HWND | 1249978 |

The catalogue tile reads “Zoom Longline Shirt”, “$49.00 – $54.00”, and “Choose size & colour”. Opening it shows “Tap a size and colour” with Navy and Sand, sizes S and M, and the branch stock counts (Navy S is 0, the other cells are 8). Prices on the grid are $49.00 and $54.00. The dialog does not contain “Portion size”, “Small Plate”, or the restaurant quantity stepper.

Grocery and electronics used earlier builds of the same executable path. Those files were replaced by the next profile build, so only this fashion hash is still on disk. Each window’s identity, PID, and data directory were recorded while that process was running.

Screenshots: `docs/ui-ux/quantity-profile-evidence/fashion-missing.png` (the catalogue tile) and `fashion-zoom.png` (the size and colour grid).

## Cafe

PASSED WITH LIMITATIONS. The window is `com.axizpos.cafe.portion`, title AxizPOS Cafe Portion, API `http://127.0.0.1:18095`, database `%TEMP%\axiz-portion\cafe\axizpos_portion_cafe.sqlite`, store `portionc`, currency AED. SHA-256 `67990a3a24c8d6d57affa4a04bc77d7e2010125c60b7bc2782ca1a639d1c70b2`. PID 38612, HWND 6754838. It does not use the restaurant database.

Daal Channa opened with no portion selected. Small Plate quantity 2 showed AED 6.00, Medium Plate kept quantity 2 at AED 10.00, and Full Plate quantity 3 showed AED 27.00. The cart then held Full Plate quantity 3 and Small Plate quantity 1 as separate lines. Mineral Water had no portion section. Minus stayed at 1. A double add left Mineral Water at 1 × AED 2.00.

The Cafe preset does not include tables, so no floor was seeded. No modifier group and no recipe sale were walked. Screenshots are in `docs/restaurant/evidence/cafe/`.

## Laundry

BLOCKED. A disposable window was opened and the live register was not. Identity `com.axizpos.laundry.acceptance`, title AxizPOS Laundry Acceptance, PID 57888, HWND 460040, data directory `%APPDATA%\com.axizpos.laundry.acceptance`, API `http://127.0.0.1:18082`, database `acceptance/laundry/pgdata` on `127.0.0.1:55821`. SHA-256 `cc0f6e8ed329f044496360cff91279465882c573e3f2b450c50a1652c59f2ac9`.

The window reached Unlock register for Laundry Tenant A, Branch A. Unlock stayed on Checking, so the New Order quantity field was not reached and no laundry order was created. Screenshot: `docs/restaurant/evidence/laundry/laundry-unlock.png`.

## Physical touchscreen

NOT RUN on every profile. Windows reports a touch pad and two pen devices, including a virtual pen. It does not report a touch digitizer. No finger taps were performed.

## What changed

A second click during one Add was reaching the cart before React re-rendered the saving flag. Quantity and modifier dialogs now claim that submit immediately. The restaurant retest left one Mineral Water line at quantity 1, and a later Add raised it to 2.

Saved restaurant order lines show the stored portion name beside the product. Pricing, recipes, stock rules, and modifier prices were not changed.

## Remaining gaps

Laundry unlock did not finish, so garment quantity was not exercised. Cafe modifiers and recipes were not walked. Grocery still needs a weighed product on the scale dialog. The electronics serial picker was opened and not completed, because that register had no cached unit. Physical touchscreen acceptance remains NOT RUN.
