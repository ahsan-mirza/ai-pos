# Inventory final acceptance

Date: 20 November 2026. The acceptance API stayed on `127.0.0.1:18081`. The acceptance database volume was later published on `127.0.0.1:55733` because Windows excluded `55433`. It was not recreated and was not migrated. `.env.inventory-acceptance` was not edited. No schema change was made, so the earlier migration rehearsal was not repeated. Developer `.env` and `ai-pos.db` were not modified.

Evidence is in `acceptance/inventory/evidence/final-closure/`.

## Purchase, receiving, and transfer

A Floor Manager created three disposable products with opening quantity 10. A three-line draft totaled 1000 cents. Editing the first line to quantity 4 and unit cost 150 cents changed the total to 1300 cents. Reopening the draft returned the same total, supplier, and Store A. Placing it set the status to `ordered`. A later edit returned 422, "Only a draft with nothing received can be edited."

A one-unit receipt of each line set the order to `partially_received` and posted `PURCHASE_IN`. Receiving 99 of the first line returned 422, "Only 3 left to receive on this line." The remainder was received and the order became `received`. A second receipt of the same lines returned 422 and the on-hand quantities stayed at 14, 12, and 11. A separate three-line order was cancelled and those quantities did not change.

`PurchaseOrderCreate` has no discount and no VAT field. Sending `vat_cents` returned 422. There is no second approver. Submit places the draft.

A three-line transfer reserved 2 at Store A. A 1000-unit transfer returned 422, "Only 12 available to reserve at the source branch," and the reservation stayed at 2. Shipping moved the transfer to `in_transit`. The Floor Manager's receive returned 403, "You can only work with your own store's stock." The catalog admin received it. Source on-hand became 12, 10, and 9. Destination on-hand became 2, 2, and 2. A second transfer was cancelled and the first product's source quantity did not change. The transfer API receives the whole shipment. It has no partial receipt or discrepancy document.

Oats stayed at 2. INV-TIN stayed at 7.

## Other inventory forms

These calls used the existing APIs. The Windows screens were not clicked again.

| Form | Result |
|---|---|
| Category and subcategory | Floor Manager create 403. Catalog admin create, subcategory, and delete succeeded. |
| Brand | Floor Manager create 403. Catalog admin create and delete succeeded. |
| Unit | Floor Manager create and delete succeeded. |
| Price list | Floor Manager read 200 and create 403. Catalog admin create 201. |
| Price change | Catalog admin created a future change and cancelled it. Status `CANCELLED`. It was not applied. |
| Batches | Floor Manager list 200. |
| Serials | Grocery list 403. Serial tracking is not enabled. |
| Replenishment | Floor Manager 403. Catalog admin created a run and did not accept it. |
| Stock count | Create, one counted line, and cancel succeeded. On-hand stayed 12. |

A model matrix was not generated. Purchase discounts, VAT lines, and a second approver are not fields on the purchase-order contract.

## Images

The Open dialog belonged to `msedgewebview2` and its owner was the acceptance window. JPEG `oats.jpg`, PNG `oats.png`, and the 80×60 WebP `oats-valid.webp` were selected together. The 44-byte `oats.webp` was not selected. The disposable product `ACC-GALLERY-CLOSE` stored three images at 64×48, 64×64, and 80×60. Those sources were already under 1200 pixels, so that browse did not demonstrate downscaling. The earlier API upload of a 1600×900 WebP stored at width 1200 remains the compression evidence.

Reopening the product showed Saved photos. Moving the first photo later swapped the 64×64 and 64×48 images and left the 64×48 image primary. Removing one photo left two. Closing and opening the product again showed those two, with Earlier, Later, and Remove.

The photo button handles a browser drop. The desktop window was taking the file first. `dragDropEnabled` is now false on the production window and the acceptance window. After rebuilding the acceptance register, a JPEG drop aimed only at its webview did not add a photo. Drag-and-drop is not passed.

## Layout

The acceptance register, PID 24440, window title `AxizPOS Inventory Acceptance`, was unlocked as Floor Manager. Products, purchase orders, transfers, and stock counts were captured at 1024×768, 1280×800, 1366×768, and 1920×1080. At 1024×768 the section buttons wrap. Scrolling the inventory pane brings the product table into view, including Acceptance Oats' related rows and INV-TIN. The purchase-order line editor and the receive form were not scrolled into a separate capture. Browse and drag-and-drop were not driven.

## Unsigned installer

`dist/POS-Setup-0.1.3.exe` is the production-configured NSIS installer for identifier `com.aipos.desktop`. No certificate was configured, so signing was skipped. Both that installer and `dist/ai-pos-desktop.exe` have Authenticode status `NotSigned`. The installer SHA-256 is `6d30b8b1ceb771b099e7a75a708d98d5e702e86db1e8b2c9ca9813e5420c5b05`. It was not installed on this PC.

## Status

| Area | Result |
|---|---|
| Multi-line purchasing | PASSED WITH LIMITATIONS |
| Receiving | PASSED |
| Multi-line transfers | PASSED WITH LIMITATIONS |
| Inventory forms | PASSED WITH LIMITATIONS |
| Windows gallery | PASSED WITH LIMITATIONS |
| Unsigned production installer | PASSED — UNSIGNED |
| Responsive document screens | PASSED WITH LIMITATIONS |
