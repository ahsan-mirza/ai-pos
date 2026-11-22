# Laundry Phase 3.1 POS UX acceptance

A frontend upgrade of the existing laundry floor. The production API, order IDs, garment IDs, tags, prices, payments, and the offline queue are unchanged. No developer, inventory, or production database was migrated. Nothing was deployed.

## What changed on the register

The Phase 3 floor put every station on an orange button and left intake as unlabeled native fields. The replacement uses the existing AxizPOS tokens: orange only for the primary action, charcoal text, white cards, and a light page background.

Shared pieces live in `apps/desktop/src/features/laundry/ui.tsx`: page header, grouped station navigation, metric cards, status badges, garment and order cards, the garment editor, scan input, customer and service selectors, weight input, photo upload, order and payment summaries, the production board, exception panel, timeline, empty and error states, and sync status.

Navigation is grouped into Daily operations, Production, and Management. A station is still hidden when the signed-in permissions do not allow it. Below the `md` breakpoint the stations collapse into one menu. Pending counts from the production board sit on Sorting, Production, Machines, Quality, Rework, Packing, Ready, and Incidents.

The dashboard reads the live board. On the acceptance preview it showed 7 received today, 5 awaiting sorting, 1 in processing, and 2 ready, with stage counts and the latest garment tags. Metric cards open the matching station. Quick actions follow the same permission list.

Order intake is a wide garment editor plus a summary. Labels cover customer, branch, order type, promise time, service, quantity, garment type, description, brand, colour, fabric, size, condition, stains, care, photos, deposit, and discount when the user may discount. The summary counts garments, bags, and net weight and says the server calculates tax and the total. Create Order is the primary button. Create and print receipt uses the existing print path after the server accepts the order. Save draft stays disabled: the server has no draft, and a non-express order with no deposit is kept locally only when the server cannot be reached.

## Authentication and sync

A refresh keeps the cashier profile and drops the access token. The old intake then said both "This action requires a signed-in user" and "Synchronization failed" while the footer API light stayed green.

Those are different states. The footer light means the server answered a hardware check. It does not mean this window is signed in or that the laundry queue synced. The floor now says which of these failed, includes the request id when the API sends one, and offers retry only when a retry is safe. Unlocking the register restores the token. Permissions were not widened to hide the message.

After a refresh on the acceptance preview, the board returned request `1af6e111a6f84ceca07dedaaef69cc06` with the signed-in-user message, and the session banner explained the missing token. After unlock, the same board loaded.

## Scan and production screens

Scan Garment takes a tag and does not move the stage. Looking up `LD-7B77A286-01` showed Walk-in Customer, Green shirt, dry clean, stage READY, QC PASS, total 10.50, paid 0.00, due 10.50, and the existing stage history. The next-action line stayed empty because the server allows no further move.

Sorting, production, machines, quality, rework, packing, ready orders, incidents, and shift summary use the same card and the same transition, inspection, batch, cycle, packing, and incident endpoints. The production board columns follow the selected workflow template. There is no drag-and-drop. Packing shows expected, scanned, and remaining for the current screen session and leaves Complete packing off until those counts match. The server still makes the final decision. Shift summary separates the signed-in operator's events from the branch board. Ready filters keep payment separate from operational ready.

Garment history now includes `open_rework` when a rework task is open, so the register can complete that task. That is an added response field. Existing clients can ignore it.

## Business Pro

`/laundry/production` is titled Production oversight and states that routine floor work stays on the register. The same board counts loaded there: 7 received, 5 awaiting sort, 1 processing, 2 ready. Workflows, batches, machines, quality, incidents, and the production report use the same management routes with clearer cards and empty states.

## Tests and layout

Desktop vitest: 8 passed (`productionAccess.test.ts` and `floorUx.test.tsx`). Backend pytest for production, orders, and catalog: 17 passed, including the open rework id on garment history.

The acceptance preview had no horizontal overflow at 1024×768 or 1280×800. The scan screen was used at 1366×768. A separate 1920×1080 pass was not recorded.

## Native window

The acceptance executable was launched again:

- Identifier `com.axizpos.laundry.acceptance`
- PID 22948
- Path `D:\Work\ai-pos\apps\desktop\src-tauri\target\debug\ai-pos-desktop.exe`
- Window title `AxizPOS Laundry Acceptance`
- Window handle 6226376

The signed-in dashboard, intake, and scan walk above is the acceptance preview in the browser. The fresh native webview was not clicked through. The installed register was not used.

## Limitations

- The native webview still needs its own unlock before the same clicks are repeated inside it.
- Packing reconciliation on screen counts scans made in that visit. A repeat scan is rejected by the server and does not increase the count.
- There is no server draft and no pause stage.
- Stage, batch, and machine changes stay disabled offline.
- An incident still does not create a refund.
- Order photos remain order evidence, not a separate photo on every garment line.

## Exit

**UI:** UI COMPLETE WITH LIMITATIONS
