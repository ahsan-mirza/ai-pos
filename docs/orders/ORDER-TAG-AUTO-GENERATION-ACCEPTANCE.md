# Automatic order tags

Date: 23-11-2026

Status: **PASSED WITH LIMITATIONS**

Takeaway tags are issued once, shown read-only, and kept when the guest or pickup time changes. This window issued `TW001`, kept it after the guest edit, settled that ticket, then issued `TW002`. Both tags were still in the register database after the isolated app was restarted. Offline tag issuance and the 125%, 150%, and 200% zoom checks were not walked on this window.

## Model

The kitchen order number (`OpenOrder.number`) is unchanged. It is still the daily store sequence. The guest tag is a separate value, not a second invoice number.

| Surface | Where it lives | Shape |
| --- | --- | --- |
| Server | `order_tags.id` is the order or session UUID. Unique on `(tenant_id, store_id, tag)`. | `TW001`, `DL001` |
| Counter | `order_tag_counters` per tenant, store, and service type. Locked and incremented in the same transaction. | monotonic, not reset each day |
| Register | SQLite `order_tags` and `table_sessions.table_number` | the same tag the cashier saw |
| Offline | Local allocate when the server call fails | `TW-{device}-{nnn}` or `DL-{device}-{nnn}` |

Dine-in keeps the table label. A presented server-format tag such as `TW009` is rejected. An offline-format tag that was already shown is accepted and is not renumbered. Repeating the same session id returns the original tag and does not write another audit row. A legacy typed tag such as `TW1` is kept. Placeholders `Takeaway` and `Delivery` are replaced once.

The register asks the server first. If SQLite already has a tag for that session, it returns that tag and does not call the server. The Update action sends the guest name, phone, and pickup time. It does not send a replacement tag. The API order update schema has no tag field, so a patched `display_tag` is rejected.

## Native evidence

| Item | Value |
| --- | --- |
| Executable | `D:\Work\ai-pos\acceptance\ordertags\target\debug\ai-pos-desktop.exe` |
| Product | AxizPOS Order Tag Acceptance |
| Identifier | `com.axizpos.ordertags.acceptance` |
| Data directory | `C:\Users\ahsan\AppData\Roaming\com.axizpos.ordertags.acceptance` |
| API | `http://127.0.0.1:18096` |
| API database | `%TEMP%\axiz-ordertags\axizpos_ordertags.sqlite` |
| Size | 31,714,304 bytes |
| SHA-256 | `4E1603CC4F790D6EFB9405B5512FBD69843502309EC7D23F6146FD2962675091` |
| Window | AxizPOS Order Tag Acceptance |

The production identifier `com.aipos.desktop` was not used. No production database was opened.

On the disposable restaurant register, signed in as Tag Owner:

1. The first takeaway was issued `TW001`. The order-tag input was read-only (`Order tag=TW001:ro`). The header read `Takeaway - Order #TW001`.
2. Customer name was changed to Bilal, phone to `0502222222`, and pickup to `15:45`. The tag stayed `TW001`.
3. Mineral Water was charged on card. Invoice `TAGREG-TG1-000001`. The receipt prompt was skipped. No drawer-kick row was written.
4. The next takeaway was issued `TW002` for Noor.
5. After the process was stopped and started again, SQLite still had both tags. `TW001` was `CLOSED`. `TW002` was `OPEN`.

Server `order_tags` matched the register: `TW001` and `TW002`, source `server`, counter `last_value` 2. Audit rows `order.tag_issued` exist only for those two issues. The settled open order kept the name Bilal and the same id as `TW001`.

Screenshots: `docs/orders/evidence/takeaway-tag.png` and `docs/orders/evidence/settings-after-restart.png`. The machine-readable walk is `docs/orders/evidence/ordertags.json`.

## Tests

`apps/api/.venv/Scripts/python.exe -m pytest tests/test_order_tags.py tests/test_orders.py -q --tb=short`

The first combined run was 1 failed, 12 passed. The failure was an unknown store reported as 409. A missing store now returns 404. `tests/test_order_tags.py` was then 1 passed in 1.95s. The order file's 12 tests had already passed with tag binding in place. The tag test covers `TW001` then `TW002`, replay, a forged `TW009`, an offline tag, a delivery `DL001`, a tag that stays put when the guest name is patched, and a rejected manual tag on update.

From `apps/desktop`:

`pnpm exec vitest run src/features/printing/printerSettingsModal.test.tsx src/features/checkout/fnb/tableSessions.test.ts src/components/shell/deviceStatus.test.ts src/features/printing/printPolicy.test.ts --reporter=dot`

4 files, 23 tests, 0 failed, exit 0.

From `apps/desktop/src-tauri`:

`cargo test --offline --lib printer::` — 13 passed, 0 failed.

`cargo test --offline --lib -- order_tags_are_unique one_compatible_printer an_explicit_missing` — 3 passed, 0 failed.

The Rust tag test checks a unique local tag, a stable re-read, and a rejected typed replacement.

## Limitations

- The native walk was online. The offline `TW-{device}-{nnn}` path was covered by the Rust test and the API offline-tag case, not by disconnecting this window.
- Zoom at 125%, 150%, and 200% was not applied to this window. The field uses the same control height as Customer name and Phone.
- A cashier login was not repeated on this window. Tag issue still goes through the existing `pos:orders` scope, and a store-bound cashier cannot issue a tag for another store.
- Alembic revision `20261123_0136` was not applied to a protected database. The disposable API built the tables with `create_all`.
