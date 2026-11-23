# Unified quantity and portion modal

Date: 23-11-2026

Overall: **PASSED WITH LIMITATIONS**

| Workstream | Result |
| --- | --- |
| Restaurant native interaction | PASSED WITH LIMITATIONS |
| Restaurant zoom | PASSED WITH LIMITATIONS |
| Physical touchscreen | NOT RUN |
| Cafe | PASSED WITH LIMITATIONS |
| Grocery | PASSED WITH LIMITATIONS |
| Electronics | PASSED WITH LIMITATIONS |
| Fashion | PASSED WITH LIMITATIONS |
| Laundry | BLOCKED |

No sale was settled. The installed register and the live laundry register were not opened. The cross-profile record is `docs/ui-ux/POS-QUANTITY-PORTION-CROSS-PROFILE-ACCEPTANCE.md`.

## Register

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.restaurant.zoom` |
| Title | AxizPOS Restaurant Zoom |
| Executable | `apps/desktop/src-tauri/target/zoom-shared/debug/ai-pos-desktop.exe` |
| Size | 31,633,920 bytes |
| SHA-256 | `da54bd42cd6263816feb2102d9474ffe2a6e99dc37e3596727b27d6519310018` |
| PID | 44192 |
| HWND | 3082512 |
| Data directory | `%APPDATA%\com.axizpos.restaurant.zoom` |
| API | `http://127.0.0.1:18093` |
| Database | `%TEMP%\axiz-zoom\restaurant\axizpos_zoom_restaurant.sqlite` |
| Store code | `rzoom` |
| Currency | AED |

That process was closed after the run. Later grocery, electronics, and fashion builds replaced the same executable path. The hash above is the build that ran this restaurant window.

Daal Channa (Small Plate AED 3.00, Medium Plate AED 5.00, Full Plate AED 9.00) and Mineral Water (AED 2.00) were created on that disposable database with opening stock of 20. Stock rules were not changed.

The exact accessible-name matcher lives only in the acceptance click driver, `apps/desktop/src-tauri/src/zoom.rs`. It matches an `aria-label` or a `title` as well as visible text, and it can target a cart line. It is compiled into the acceptance window. Production accessibility labels were not changed.

## Restaurant native interaction

| Test | Status | Evidence |
| --- | --- | --- |
| Portion selection | PASS | Daal opens with no portion selected and Add reading “Add to sale”. Small quantity 2 shows AED 6.00. Full quantity 3 shows AED 27.00. |
| Quantity stepper | PASS | Minus at 1 stays on “Add 1 — AED 2.00”. Plus moves to “Add 2 — AED 4.00”. |
| Manual quantity validation | PASSED WITH LIMITATIONS | Empty, 0, and `abc` leave Add disabled. 1, 2, and 9999 are accepted (9999 shows AED 19,998.00). The field keeps digits only, at most four, so `-1` becomes 1, `1.5` becomes 15, and `10000` becomes 1000. None of those inputs can be submitted as a negative, decimal, or five-digit quantity. |
| Add duplicate prevention | PASS | Two clicks in the same confirmation left Mineral Water at 1 × AED 2.00. A later Add of the same product raised that line to 2 × AED 2.00. Small Plate and Full Plate stayed separate lines. |
| Cart line editing | PASS | Small Plate quantity 2 and Full Plate quantity 3 stayed separate. Editing Small to 4 left Full at 3 × AED 9.00. Opening Full restored “Update 3 × Full Plate — AED 27.00”. Cancel left both lines unchanged. |
| Modifier integration | PASSED WITH LIMITATIONS | Grilled Chicken showed Breakfast AED 8.00, Lunch AED 12.00, Dinner AED 15.00, Extra cheese AED 1.50, and the shared stepper. One line was added: Breakfast, Extra cheese, 2 × AED 9.50, line amount AED 19.00. That unpaid line was not opened again for edit. |
| Dine-in draft | PASSED WITH LIMITATIONS | Table Z1 seated 2 guests and shows Occupied, AED 10.00. The saved unpaid order is Daal Channa, Medium Plate, quantity 2, unit price 500 cents. The order-line panel was outside the 1400×900 capture. |
| Takeaway draft | PASS | Unpaid takeaway order: Daal Channa, Full Plate, quantity 3, unit price 900 cents. |
| Delivery draft | PASS | Unpaid delivery order on channel Accept Drop, reference ACC-9: Daal Channa, Small Plate, quantity 2, unit price 300 cents. |

The first duplicate-add attempt created 2 × Mineral Water from one confirmation, because the dialog’s saving flag updates on the next render. Quantity and modifier dialogs now claim the submit synchronously. A refused add releases the claim so the cashier can correct it. A later Add of the same single-price product still merges onto that line, which is the existing cart rule. Different portions do not merge.

Saved order lines now include the stored portion name in the line label. The photographed dine-in frame shows the table amount, not that label, because the order panel sits past the right edge of the 1400×900 capture. The portion name, option id, quantity, and unpaid state are on the saved order.

The 100% cart captures (`cart-two-lines.png`) show the catalogue. The cart panel itself is in `zoom-200.png`: Current sale, 11 items, Daal Channa Small Plate quantity 4 at AED 3.00, and Daal Channa Full Plate quantity 3 at AED 9.00.

Screenshots and the measurement file are in `docs/restaurant/quantity-modal-evidence/`.

## Zoom

WebView zoom was set with `window.set_zoom`. Root font stayed `16px`. `visualViewport.scale` stayed 1. There was no document-level horizontal overflow. The portion dialog’s body scrolls when the viewport is short. The dialog element itself does not grow a second scrollbar.

| Zoom | devicePixelRatio | Portion list | Quantity controls | Total | Add/Cancel | Horizontal overflow |
| --- | --- | --- | --- | --- | --- | --- |
| 100% | 1.75 | All three cards inside the viewport | Minus, field, and plus inside | AED 5.00 for Medium × 1 | Both inside | No |
| 125% | 2.1875 | All three inside | All inside | Visible in the dialog text | Both inside | No |
| 150% | 2.625 | All three inside; the body can scroll | All inside | Visible | Both inside | No |
| 200% | 3.5 | All three inside before scrolling. After scrolling the body, one card leaves the viewport and remains reachable by scrolling | Probe places minus, field, and plus inside. The 1400×900 bitmap shows the quantity field and cuts the plus control at the right edge | Visible in the dialog text | Probe places both inside the WebView | No |

The earlier 200% capture that cut the Medium card at the image edge was the bitmap boundary of the 1400×900 window, not a document scrollbar. At 200% the layout viewport is 693×432 CSS pixels, `devicePixelRatio` is 3.5, and the portion body scrolls. Add and Cancel stay in the layout viewport while a scrolled card moves out of it.

## Physical touchscreen

NOT RUN. This machine exposes:

- HID-compliant touch pad (`HID\CUST000&COL03\...`)
- HID-compliant pen (`HID\VMULTI&COL03\...`), a virtual device
- HID-compliant pen (`HID\{00001124-...}_VID&00010075_PID&0100&COL03\...`)

No HID-compliant touch screen or touch digitizer was present. The clicks in this run were the acceptance driver scoped to the acceptance window. They are not finger taps.

## Automated tests

From `apps/desktop`:

`pnpm exec vitest run src/features/checkout/quantityModal.test.tsx src/features/checkout/priceOptionModal.test.tsx src/features/checkout/cart.test.ts --reporter=dot`

3 files, 31 tests, 0 failed, exit 0. The new test covers the synchronous submit claim.

`pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

## Evidence closure, 23-11-2026

The earlier process was not running, and starting the disposable API replaces its SQLite file. The Z1 line and the chicken line were created again on a new disposable database, then inspected. No sale was settled.

| Item | Value |
| --- | --- |
| Identity | `com.axizpos.restaurant.zoom` |
| Title | AxizPOS Restaurant Zoom |
| Executable | `apps/desktop/src-tauri/target/zoom-shared/debug/ai-pos-desktop.exe` |
| Size | 31,638,528 bytes |
| SHA-256 | `793183653205cc8d38532da3e323334a7497ddbc2f9ff54501d3b13ab3537502` |
| PID | 9696 |
| HWND | 3802388 |
| API | `http://127.0.0.1:18093` |
| Database | `%TEMP%\axiz-zoom\restaurant\axizpos_zoom_restaurant.sqlite` |

The window was placed at 1000×1200 so the order sheet covers the frame. `docs/restaurant/quantity-modal-evidence/restaurant-z1-medium-plate-order-line.png` shows Table Z1, Occupied, Kitchen: New, Daal Channa · Medium Plate, 2 × AED 5.00, and the line status New. The saved order is OPEN, quantity 2, unit 500 cents, `price_option_name` Medium Plate, `paid_sale_id` null.

`restaurant-grilled-chicken-edit-restored.png` shows Breakfast selected and Extra cheese selected. The same dialog’s measured text includes unit AED 9.50 and Update item AED 19.00. Those two amounts sit below the visible frame. Cancel left the cart line at 2 × AED 9.50, AED 19.00, Breakfast, Extra cheese.

The same desktop tests were run again: 3 files, 31 tests, 0 failed, exit 0. `pnpm exec tsc -p tsconfig.json --noEmit` exit 0.

Cafe and laundry are recorded in `docs/restaurant/RESTAURANT-CAFE-LAUNDRY-NATIVE-ACCEPTANCE.md`. Grocery, electronics, and fashion were not launched again. Physical touchscreen acceptance stays NOT RUN. This machine has a touch pad and two pen devices, and no touch digitizer.
