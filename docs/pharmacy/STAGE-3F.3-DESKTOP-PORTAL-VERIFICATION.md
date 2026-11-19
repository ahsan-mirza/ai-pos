# Stage 3F.3 — Desktop, tenant cache, and Business Pro portal

Acceptance and verification only. No production deployment, production migration, or production tenant activation was performed.

## Outcomes

| Area | Result |
| --- | --- |
| Tenant cache | **NOT RUN** |
| Windows Pharmacy register | **NOT RUN** |
| Offline and synchronization behavior | **NOT RUN** |
| Business Pro portal | **PASSED WITH LIMITATIONS** |
| Overall software implementation | **TECHNICALLY COMPLETE WITH LIMITATIONS** |
| Production authorization | **APPROVAL PENDING** |

Installer signing remains **BLOCKED — CERTIFICATE REQUIRED**. `AXIZPOS_SIGN_THUMBPRINT` was unset. Signing was not disabled and no thumbprint was invented.

Stage 3F.2 remains the record for PostgreSQL transaction behavior, the `ai_pos_app` role, RLS, and migration `20261119_0119` to `20261119_0120`. Those tests were not repeated.

## Safety gate

The inventory acceptance register was running before any Pharmacy work and was still running after cleanup.

| Item | Value |
| --- | --- |
| PID | 59572 |
| Executable | `D:\Work\ai-pos\acceptance\inventory\target\release\ai-pos-desktop.exe` |
| Visible windows | 26480636 `com.axizpos.inventory.acceptance-siw`; 28774662 `AxizPOS Inventory Acceptance` |
| Identity | `com.axizpos.inventory.acceptance` |
| WebView data | `C:\Users\ahsan\AppData\Local\com.axizpos.inventory.acceptance\EBWebView` |
| API | `http://127.0.0.1:18081` (listener PID 37356) |
| Database | `axizpos-inventory-acceptance-db` at `127.0.0.1:55433` |

That process was not closed, clicked, or given keyboard input. No second AxizPOS register was launched. Pharmacy desktop acceptance is **BLOCKED — INVENTORY ACCEPTANCE SESSION ACTIVE**.

## Passed — Business Pro portal

The portal was the real Business Pro page at `/sales-insights`, Transactions tab, Return, then Refund. The page posts `POST /api/v1/returns` with `Idempotency-Key`. That route calls `ingest_one` for `sale_return`, which calls `returns_service.apply_return` and then `hold_customer_return`. The original sales were created through `POST /api/v1/sync/push`. Stock was received, adjusted, recalled, and supplier-returned through the existing inventory and pharmacy endpoints. No quantity was written with SQL.

Disposable stack, removed after the run:

| Item | Value |
| --- | --- |
| API | `http://127.0.0.1:18080` |
| Portal | `http://127.0.0.1:15173` |
| Postgres | `127.0.0.1:55432` |
| Databases | `axizpos_pharmacy_acceptance`, `axizpos_pharmacy_acceptance_control` |
| Container | `axizpos-pharmacy-acceptance-db` |
| Role | `ai_pos_app` (not superuser, no bypass RLS) |
| Tenants | `pharmacy-accept` (pharmacy), `accept-grocery` (grocery), both on the existing Pro AI plan |
| Desktop identity | `com.axizpos.pharmacy.acceptance` was not launched |

The isolation guard reported no match to development, production, or the persistent database. Ports 5432, 8000, 18081, and 55433 were not used.

### Scenario A — valid medicine return

Invoice `P3F3-S-000001`, one unit from `LOT-RET` (imported 4). The portal returned 201 and showed credit note `P3F3-CN-000001`.

After the return the layer was `QUARANTINED` with 4 remaining. A later sale of that product was rejected with `lot_quarantined`. The returned unit and the units that had not been sold are on the same layer, and that layer cannot be sold.

### Scenario B — return quantity limit

The portal opened invoice `P3F3-S-000002` (one unit sold). The quantity field had `max=1`. Entering 9 left the value at 1, so the page did not submit an excess quantity.

The same receipt was then posted to `POST /api/v1/returns` with quantity 2. The API returned 422. The return list stayed at 3 rows. `LOT-EXCESS` stayed `RELEASED` with 1 remaining.

### Scenario C — status preservation

| Status | How it was reached | After the portal return |
| --- | --- | --- |
| `RECALLED` | `POST /api/v1/pharmacy/recalls` on `LOT-RECALL` after the sale | `RECALLED`, remaining 4. Portal invoice `P3F3-S-000003`, HTTP 201 |
| `SUPPLIER_RETURN` | Supplier return of the unsold unit, then the portal return of the sold unit | `SUPPLIER_RETURN`, remaining 1. Portal invoice `P3F3-S-000004`, HTTP 201 |
| `UNRELEASED` | **NOT RUN** | No existing endpoint returns a sold released layer to `UNRELEASED`. SQL was not used |
| `DAMAGED` | **NOT RUN** | No existing service writes `DAMAGED`. That workflow was not added |

### Scenario D — grocery return

Grocery tenant `accept-grocery` had no `pharmacy_catalog` capability. Invoice `G3F3-S-000001` was returned in the portal (HTTP 201, credit note `G3F3-CN-000001`). A later grocery sale succeeded. On-hand quantity after that sale was 2, which is the three received units, minus the original sale, plus the portal return, minus the later sale. The grocery product was not given a pharmacy lot status.

## Authorization recorded on this stack

These are application accounts, not evidence of two natural persons. Professional licences were not checked.

- Pharmacy profile exposed `pharmacy_catalog`. Grocery settings did not.
- Two clerks nominated and confirmed two governance officers. One officer requested the pharmacist. That officer's own approval was refused (the seed stops unless the response is 403 or 422). The second officer approved. The pharmacist then released the lots used above.
- Cashier `cashier.one` signed in with the register PIN on the acceptance device and `POST /api/v1/pharmacy/lots/{id}/release` returned 403.
- Register UI visibility for cashier, floor manager, pharmacist, catalog admin, and governance officer was **NOT RUN**, because the Pharmacy register was not opened.
- Immediate effect of a revoked pharmacist was **NOT RUN** in this stage.

## Not run

Blocked by the live inventory acceptance register:

- Tenant capability-cache load, switch, restart, stale snapshot, and missing snapshot.
- Windows online Pharmacy sale, FEFO display, and double-click Charge.
- Pharmacy offline block before invoice reservation, PIN reauthentication, and the eight header states.
- Grocery offline queue, sync-once, and restart replay.

Also not run, for the reasons in the portal section: `UNRELEASED` and `DAMAGED` preservation through the portal. Customer-return resale of a quarantined medicine was not implemented.

## Failed

No product scenario failed on the final run.

Earlier disposable databases were dropped after harness mistakes: an inherited API key, a sale posted with zero VAT, a cashier password login that the portal correctly refuses, an inherited CORS list, and a selector that did not match the return dialog. No application source file was changed.

## Database verification

Read from the disposable database before it was removed (`acceptance/pharmacy/evidence/stage-3f.3/lots.txt`):

| Lot | Status | Imported | Remaining |
| --- | --- | --- | --- |
| LOT-RET | QUARANTINED | 4 | 4 |
| LOT-EXCESS | RELEASED | 2 | 1 |
| LOT-RECALL | RECALLED | 4 | 4 |
| LOT-SUP | SUPPLIER_RETURN | 2 | 1 |

`returns_before` and `returns_after` for the excess post were both 3. Excess HTTP status was 422.

## Evidence index

`acceptance/pharmacy/evidence/stage-3f.3/`

| File | What it shows |
| --- | --- |
| `process-gate.json` | Inventory PID, executable, API port, database port |
| `desktop-blocked.txt` | Register work blocked; window titles for the same PID |
| `not-run.json` | Scenarios that were not executed |
| `isolation.txt` | Acceptance guard, then `ai_pos_app` without superuser or bypass RLS |
| `environment.txt` | Loopback API, portal, and database targets |
| `invoices.json` | Disposable invoice numbers and lot ids |
| `api-seed.json` | Pharmacy capability and cashier release refusal |
| `browser.json` | Portal return HTTP results and the quantity clamp |
| `pharmacy-return-valid.png` | Return recorded, `P3F3-CN-000001` |
| `pharmacy-return-recalled.png` | Recalled-sale return recorded |
| `pharmacy-return-supplier.png` | Supplier-return sale return recorded |
| `excess-clamp.png` | Quantity held at 1 |
| `grocery-return.png` | Grocery return recorded, `G3F3-CN-000001` |
| `api-verify.json` | Quarantine, resale rejection, excess 422, preserved statuses |
| `lots.txt` | Lot status and remaining quantity |
| `developer-before.json`, `developer-after.json` | Developer files unchanged |
| `cleanup.txt` | Pharmacy container removed |

Passwords, tokens, device keys, and environment secret values are not in that folder.

## Cleanup

- Pharmacy acceptance API and portal processes were stopped.
- `axizpos-pharmacy-acceptance-db` and its volume were removed. A later `docker ps` did not show that container.
- `.env.acceptance` and the acceptance device-key file were removed.
- Developer `ai-pos.db` stayed 286720 bytes, `terminal.bin` stayed 694 bytes, and `.env` stayed 1878 bytes, with the same modification times.
- Inventory PID 59572, `127.0.0.1:18081`, and `axizpos-inventory-acceptance-db` on `127.0.0.1:55433` were still present.
- The developer API on port 8000 and unrelated containers were not stopped.

## Remaining release risks

- Windows register acceptance, tenant-cache reactivation, double-click Charge, Pharmacy offline blocking, PIN reauthentication, header states, and Grocery offline sync are not yet observed on a running register.
- `UNRELEASED` and `DAMAGED` were not put through the portal return.
- Damaged-stock handling, customer-return resale, natural-person identity, professional licence checks, and separation of duties beyond application accounts remain external approvals.
- Installer signing is blocked until a certificate is supplied.
- Production authorization stays **APPROVAL PENDING**.
