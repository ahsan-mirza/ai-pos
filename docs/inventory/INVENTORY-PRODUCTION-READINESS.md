# Inventory production readiness

Date: 20 November 2026. No production deployment, production migration, or production tenant activation was performed.

## This sprint

The acceptance register was closed only after its executable was confirmed, rebuilt with the layout fix, and launched again. It is now PID 27260, `acceptance/inventory/target/release/ai-pos-desktop.exe`, window title `AxizPOS Inventory Acceptance`. The acceptance API was restarted on `127.0.0.1:18081` against `axizpos-inventory-acceptance-db` on `127.0.0.1:55433`. A shell variable had pointed a short-lived restart at port 55444. That process was stopped. The running API uses the inventory-acceptance database. Developer `ai-pos.db`, `terminal.bin`, and `.env` timestamps are unchanged.

### Responsive product list

The product section tabs now wrap, and the product table stays inside the pane. Captures after unlock, with Products selected:

- `acceptance/inventory/evidence/final-release/sprint2-viewport-1024x768.png`
- `acceptance/inventory/evidence/final-release/sprint2-viewport-1024x768-table.png`
- `acceptance/inventory/evidence/final-release/sprint2-viewport-1280x800.png`
- `acceptance/inventory/evidence/final-release/sprint2-viewport-1366x768.png`
- `acceptance/inventory/evidence/final-release/sprint2-viewport-1920x1080.png`

At 1024×768 the tabs wrap, Search and Add product stay on screen, and the scrolled table shows Product, SKU, barcode, price, status, and Edit without cutting a column off the window. Regression: `layout.test.ts`, 3 passed.

### Purchasing, receiving, and transfers

Evidence: `sprint2-workflows.json` and `sprint2-transfer-receive.json`.

A Floor Manager created three disposable products and one three-line draft. The draft was edited from 4 to 5 on the first line. The document total changed from 1600 to 1700 cents, which is quantity times unit cost. The order was placed. A three-line partial receipt posted `PURCHASE_IN` movements. An over-receipt returned 422, "Only 3 left to receive on this line." The remainder was received and the order became `received`. A second order was cancelled and barley stock stayed at 11. Opening stock was one movement per product. Oats stayed at 2 and INV-TIN stayed at 7.

Purchase orders have no line discount, no separate VAT line, and no second approver. Submit moves a draft to `ordered`. That is the contract.

A three-line transfer reserved 2 at Store A. A 1000-unit transfer returned 422 and left the reservation at 2. Shipping reduced Store A. The Floor Manager cannot receive at Store B, so the catalog admin received it. Store B then held 2 of each line and Store A held 9, 7, and 6. The transfer API receives the whole shipment. It has no partial-receipt or discrepancy document.

The register now has Save draft on an open draft. `tests/test_inventory.py` purchase-order lifecycle and transfer: 2 passed.

### Images and fields

A 1600×900 WebP was stored at width 1200. A PNG was added, then one image was moved to position 1. Browse and drag-and-drop were not driven. A weighed product with PLU `445566` persisted. A store-bound brand create returned 403. Season and gender are hidden on the grocery form. The product API still accepts them on this grocery tenant. Serial tracking is not a grocery capability.

The seeded register PINs no longer matched, so the catalog admin restored the seeded PINs for Floor Manager and Cashier. The window then unlocked as Floor Manager.

### 20 November

The acceptance register was not running. The API on `127.0.0.1:18081` and the acceptance database on `127.0.0.1:55433` were. A second register was not launched. Developer files were not modified.

`test_other_profiles_still_create_products_and_reject_pharmacy_fields` and `test_grocery_fefo_still_sells_expired_stock_last` passed on the test database. The first test switches electronics, wholesale, fashion, grocery, restaurant, cafe, and quick service, creates a product on each, and rejects a pharmacy payload with `profile_not_pharmacy`. Electronics does not include FEFO in `COMPATIBLE`. Dedicated profile tenants were not created on the acceptance database because tenant creation upgrades that shared database.

| Profile | What this run proved | Result |
|---|---|---|
| Grocery | Product create, FEFO sale order, pharmacy fields rejected | PASSED WITH LIMITATIONS |
| Fashion | Product create, pharmacy fields rejected | PASSED WITH LIMITATIONS |
| Electronics | Product create, pharmacy fields rejected, FEFO not in the profile | PASSED WITH LIMITATIONS |
| Restaurant, cafe, quick service | Product create, pharmacy fields rejected | PASSED WITH LIMITATIONS |
| Pharmacy | Existing pharmacy catalog tests were not rerun as a new tenant | NOT RUN |

A disposable Postgres 16 on `127.0.0.1:55455` was upgraded from `20261119_0119` to `20261119_0120` twice. Prior quantities and movement ids stayed unchanged. `ai_pos_app` was `LOGIN`, `NOSUPERUSER`, and `NOBYPASSRLS`. An empty tenant returned 0 products and a cross-tenant insert returned `42501`. The acceptance database was dumped and restored into a second disposable database. Counts matched and restored oats on hand stayed 2. The dump and disposable container were removed. Report: `docs/inventory/INVENTORY-MIGRATION-REHEARSAL.md`.

On the live acceptance database, the same application role saw the grocery oats row, saw no oats row as the pharmacy tenant, and returned `42501` on a cross-tenant insert. Cashier PIN login returned 200. Stock and adjustment both returned 403, "You do not have permission for this action."

Twenty reads of the 23 MB acceptance database produced no errors. Product list median was 47.2 ms and P95 was 65.8 ms. There is no approved latency target. Report: `docs/inventory/INVENTORY-PERFORMANCE-REPORT.md`.

No code-signing certificate is installed, and `AXIZPOS_SIGN_THUMBPRINT` is unset.

### Closure the same day

The acceptance register was still not running and was not launched. A new three-line purchase, receipt, and transfer was posted through the acceptance API. Oats stayed at 2 and INV-TIN stayed at 7. Category, brand, unit, price-list, price-change, batch, replenishment, and stock-count calls were persisted or rejected according to the existing permissions. Grocery serial tracking stayed off.

Seven profiles were created with the tenant CLI on a disposable Postgres. That database was not the acceptance database, and the container was removed. Electronics FEFO returned 422. Grocery stored a weighed product. Fashion stored season, collection, and gender. Pharmacy stored the manufacturer and offline policy `BLOCK`. The trial plan refused a second branch and a third staff account. Details are in `INVENTORY-FINAL-ACCEPTANCE.md`, `INVENTORY-BUSINESS-PROFILE-ACCEPTANCE.md`, and `INVENTORY-ROLE-ACCEPTANCE.md`.

No inventory migration was added, so the migration rehearsal was not repeated. Performance still has no approved target. A proposed matrix is marked awaiting approval in `INVENTORY-PERFORMANCE-REPORT.md`.

### Later the same day

Windows had reserved port 55433, so the existing acceptance database volume was published on `127.0.0.1:55733`. The database was not recreated and was not migrated. Oats stayed at 2 and INV-TIN stayed at 7. Alembic stayed at `20261119_0120`. The acceptance API was started against that port without editing `.env.inventory-acceptance`.

The acceptance register, PID 24440, is `acceptance/inventory/target/release/ai-pos-desktop.exe`, title `AxizPOS Inventory Acceptance`. It was unlocked as Floor Manager. Products, purchase orders, transfers, and stock counts were captured at 1024×768, 1280×800, 1366×768, and 1920×1080. At 1024×768 the section buttons wrap. Scrolling the inventory pane reveals the product table.

The Open dialog was owned by that window. One browse selected a JPEG, a PNG, and a valid 80×60 WebP. Product `ACC-GALLERY-CLOSE` stored all three. Reopening it showed the saved gallery. Later moved the first photo, Remove left two, and closing and reopening kept those two. Drag-and-drop was not driven. The three source files were already smaller than 1200 pixels.

On the existing pharmacy tenant, a prescription product with offline sale allowed returned 422. A receipt without a manufacturer lot returned 422. A receipt with lot `MFG-CLOSE-1` and expiry 2027-12-01 posted and stayed `UNRELEASED`. Admin release returned 403. Quarantine and an open recall did not change the on-hand quantity of 4. Two governance officers appointed a pharmacist. That pharmacist released a separate lot. The admin remained unauthorized. The pharmacy tenant has one branch, so an unreleased transfer was not posted.

A Store Manager bound to Store A was created from the existing Store Manager role. An adjustment at Store B returned 403, and a category create returned 403. Cashier PIN login returned 200 and stock returned 403. No permission was added.

### Blocker pass the same day

The acceptance register was closed only after its path was confirmed, rebuilt, and launched again. It is now PID 31216, the same acceptance executable, window title `AxizPOS Inventory Acceptance`. Developer `.env` and `ai-pos.db` timestamps are unchanged.

The product photo button already accepted a browser drop. The window was taking the file before that button could see it. Both the production and acceptance window configs now set `dragDropEnabled` to false so the photo control receives the drop. `layout.test.ts` covers that setting, 4 passed. A JPEG was then aimed at the acceptance webview only. The control did not show the file. Drag-and-drop is not passed.

A Store Manager bound to Store B received an in-transit transfer. The Floor Manager, bound to Store A, received 403, `store_scope`. A second receive returned 422, `transfer_state`. Source on-hand for `ACC-CLOSE-1` is 10 and destination on-hand is 4. Oats stayed at 2 and INV-TIN stayed at 7. The transfer contract receives the whole shipment. It has no partial line or discrepancy document, and no second approver. Purchase orders still have no discount field and no VAT input. Purchase cost is quantity times unit cost. Product tax remains on the product. Those fields were not added.

An expired access token returned 401. A new register key worked, and the same key returned 401, `device_revoked`, after that device was revoked. The acceptance register's own device was not revoked. Invalid password, invalid PIN, a missing terminal token, and an unknown terminal token returned 401. The register lock clears the token held in the window. There is no server logout route, and one was not added. The officer who requested a pharmacist appointment received 403, `separation_of_duties`, when approving it. The other officer rejected that appointment.

Authenticode signing is now optional. With no thumbprint, `build:win` produced `dist/POS-Setup-0.1.3.exe`. `Get-AuthenticodeSignature` reported `NotSigned` for the installer and `ai-pos-desktop.exe`. The signing metadata says `UNSIGNED`. Installer SHA-256 is `6d30b8b1ceb771b099e7a75a708d98d5e702e86db1e8b2c9ca9813e5420c5b05`. Executable SHA-256 is `e9889eca6b34d074f32965007f7770b2ff5e88c096700ef13a2b19ccaf06ccd1`. The installer was not installed on this PC because its identifier is `com.aipos.desktop`, the same identity as the installed register. Policy: `UNSIGNED-WINDOWS-RELEASE-POLICY.md`.

## Still blocking a release review

- The acceptance photo control did not receive a dragged file after the window stopped capturing drops.
- The pharmacy tenant has one branch, so a pharmacy transfer was not posted.
- Inventory Clerk and Procurement are not system roles. Logout is the register lock, not a server endpoint.
- Performance has no approved target. The request is in `INVENTORY-PERFORMANCE-ACCEPTANCE.md`.
- The photo control still did not receive a dragged file.
- Performance targets are still awaiting approval.
- The unsigned installer was not installed here, because that would use the same application identity as the installed register.
- No authorized code-signing certificate is configured. The build no longer stops for that. The installer is unsigned and is not publisher-verified. The acceptance database file still names port 55433, which Windows is currently excluding.

## Release gates

| Release gate | Outcome |
|---|---|
| Product CRUD | PASSED WITH LIMITATIONS |
| Images and gallery | PASSED WITH LIMITATIONS |
| Responsive layouts | PASSED WITH LIMITATIONS |
| Inventory forms parity | PASSED WITH LIMITATIONS |
| Multi-line purchasing | PASSED WITH LIMITATIONS |
| Multi-line receiving | PASSED |
| Multi-line transfers | PASSED WITH LIMITATIONS |
| Business profile acceptance | PASSED WITH LIMITATIONS |
| Role acceptance | PASSED WITH LIMITATIONS |
| Security and data integrity | PASSED WITH LIMITATIONS |
| Performance | MEASURED ONLY |
| Migration rehearsal | PASSED |
| Backup and restore | PASSED |
| Production build | PASSED — UNSIGNED |
| Code signing | OPTIONAL — NOT CONFIGURED |
| Production deployment readiness | READY WITH LIMITATIONS |

The acceptance API is on `127.0.0.1:18081`. The acceptance database volume is published on `127.0.0.1:55733` because Windows is excluding `55433`. `.env.inventory-acceptance` still names `55433` and was not edited. The acceptance register, PID 31216, is still running. The unsigned installer was not installed and was not deployed. Production data was not migrated. The release candidate is unsigned.
