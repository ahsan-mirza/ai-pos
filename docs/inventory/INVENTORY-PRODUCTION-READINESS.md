# Inventory production readiness

Date: 19 November 2026. No production deployment, production migration, or production tenant activation was performed.

## What this sprint verified

The acceptance register is running as PID 62684 from `acceptance/inventory/target/release/ai-pos-desktop.exe`. Its window title is `AxizPOS Inventory Acceptance`. Diagnostics record identifier `com.axizpos.inventory.acceptance`, API `http://127.0.0.1:18081`, and `developer_env_loaded` false. UI Automation was scoped to that process.

A Floor Manager used that window to create, update, and archive `Acceptance Millet 250g Revised` (`7781832f-cdd2-46fb-b489-83f07f2b1aff`). The saved row is SKU `ACC-MILLE-250G`, barcode `2008255702111`, 375 cents, one opening-balance movement of 1 at Acceptance Store A, then inactive. The same window rejected a duplicate SKU and a duplicate barcode. No `ACC-DUP-PROBE` row was inserted. The reference oats row and `INV-TIN` were not edited.

The purchase-order tab on that window shows `Add line`, `Create order`, and the notice that an order does not increase stock. An earlier two-line order for oats and `INV-TIN` was created and cancelled without a stock movement. A transfer that reserves stock was not posted. Receiving that posts stock was not run.

JPEG and PNG fixtures uploaded to the millet product through the product image API, returned 201, and were re-encoded at 64 pixels. One image was deleted (204). A text file returned 415. A file over 5 MB returned 413 `Photos are limited to 5 MB.` The 44-byte WebP fixture was rejected as not a photo. Browse and drag-and-drop were not driven, because a file dialog is a desktop-wide window.

Window captures at 1024×768, 1280×800, 1366×768, and 1920×1080 are in `acceptance/inventory/evidence/final-release/`. At 1024×768 the product table and tab row are clipped.

Desktop typecheck passed. Vitest `documentLines`, product payload, and inventory tabs: 16 passed, exit 0. Pytest purchase-order lifecycle, transfer, opening stock, and other-profile pharmacy rejection: 4 passed, exit 0.

## Still blocking a release review

- Gallery browse, drag-and-drop, reorder, and a valid WebP photo were not completed on the window.
- Brand, season, gender, weighed goods, and serial fields were not exercised on the live form.
- Partial and full receiving that posts stock, and a multi-line transfer that moves stock, were not executed.
- Fashion, electronics, restaurant, cafe, quick service, and pharmacy were not accepted on separate disposable tenants.
- `ai_pos_app` with `NOBYPASSRLS` was not used for the acceptance SQL. Those checks used the database owner.
- No performance sample was measured, and no fresh-database migration or backup restore was rehearsed.
- `AXIZPOS_SIGN_THUMBPRINT` is unset. The signing check was not disabled. No production installer was produced.

## Environment

The acceptance API on `127.0.0.1:18081` and `axizpos-inventory-acceptance-db` on `127.0.0.1:55433` are still up. The acceptance register PID 62684 was left running. When rechecked after the viewport captures, installed PID 33672 was no longer running. Its executable timestamp (11 November 2026) and the developer `ai-pos.db`, `terminal.bin`, and `.env` timestamps were unchanged. No close or input was sent to that process.

## Release gates

| Release gate | Outcome |
|---|---|
| Product CRUD | LIMITED |
| Images and gallery | LIMITED |
| Inventory forms parity | IN PROGRESS |
| Multi-line purchasing and receiving | LIMITED |
| Multi-line transfers | LIMITED |
| Business profile acceptance | NOT RUN |
| Security and data integrity | LIMITED |
| Performance | NOT RUN |
| Migration and recovery | BLOCKED |
| Production build | BLOCKED |
| Code signing | BLOCKED — CERTIFICATE REQUIRED |
| Production deployment readiness | BLOCKED |
