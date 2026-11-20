# Final-release evidence index

Date: 20 November 2026. On the morning check the acceptance register was not running. The API remained on `127.0.0.1:18081` and the database on `127.0.0.1:55433`. No second register was launched.

Earlier the same programme used PID 27260, `acceptance/inventory/target/release/ai-pos-desktop.exe`, title `AxizPOS Inventory Acceptance`. UI Automation was limited to that process. The corrected layout captures are `sprint2-viewport-*.png`. The older `viewport-*.png` files show the clipped layout and are not the fix.

Sprint 2 evidence is `sprint2-workflows.json`, `sprint2-transfer-receive.json`, and `sprint2-viewport-*.png`. At 1024×768 the product tabs wrap and Add product plus the table columns stay in the window. Oats remained on hand 2. INV-TIN remained on hand 7.

| Scenario | Evidence | Role | Tenant | Viewport | Result |
|---|---|---|---|---|---|
| Reference oats and INV-TIN | stage-1.2.4/database-oats.json | Floor Manager | inv-accept | n/a | Unchanged |
| Millet create, update, archive | final-release/millet.json and the product list on the window | Floor Manager | inv-accept | live window | Persisted. One opening movement. Then inactive |
| Duplicate SKU and barcode | acceptance window messages | Floor Manager | inv-accept | live window | "SKU is already in use." and "Barcode is already in use." No ACC-DUP-PROBE row |
| JPEG and PNG upload, then delete one | final-release/millet.json | Floor Manager | inv-accept | API | 201, then 204. One image remains |
| 44-byte WebP fixture | final-release/millet.json | Floor Manager | inv-accept | API | 415, not a photo |
| Text file | final-release/millet.json | Floor Manager | inv-accept | API | 415 |
| File over 5 MB | final-release/millet.json | Floor Manager | inv-accept | API | 413 Photos are limited to 5 MB |
| Browse and drag-and-drop | not driven | Floor Manager | inv-accept | live window | File dialog is desktop-wide |
| Four window sizes | viewport-1024x768.png, viewport-1280x800.png, viewport-1366x768.png, viewport-1920x1080.png | Floor Manager | inv-accept | those sizes | 1024×768 clips the product table and tab row |
| Purchase-order form | acceptance window | Floor Manager | inv-accept | 1920×1080 | Add line and Create order are present. No new order was submitted |
| Two-line order, then cancel | stage-1.2.4/follow-up.json | Floor Manager | inv-accept | API | 201, then cancelled. Stock unchanged |
| Transfer that moves stock | not posted | n/a | inv-accept | n/a | Create would reserve source stock |
| Enrolled device and cashier stock | stage-1.2.4/follow-up.json | Device, Cashier | inv-accept | API | Product list 200. Stock 403 |
| Production installer | not produced | n/a | n/a | n/a | AXIZPOS_SIGN_THUMBPRINT unset. No code-signing certificate is installed |
| Upgrade from 20261119_0119 | final-release/migration-rehearsal.json | ai_pos_app | disposable | n/a | Head 20261119_0120. Second upgrade changed nothing. Quantities unchanged |
| Backup and restore | final-release/migration-rehearsal.json | owner, then disposable | inv-accept source | n/a | Restore exit 0. Counts matched. Restored oats on hand 2 |
| Application-role isolation | final-release/performance-and-rls.json | ai_pos_app | inv-accept | n/a | Grocery sees oats. Pharmacy does not. Empty tenant sees 0. Cross insert 42501 |
| Cashier stock and adjustment | final-release/performance-and-rls.json | Cashier | inv-accept | API | PIN 200. Stock 403. Adjustment 403 |
| Latency sample | final-release/performance-and-rls.json | Floor Manager | inv-accept | API | Measured. No approved target |
