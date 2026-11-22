# Laundry Phase 3 acceptance

POS-first production on the disposable laundry database. No developer database, inventory acceptance database, or production database was migrated. Nothing was deployed.

## What was proven

Migration `20261121_0123` is the head of `axizpos_laundry_acceptance` only. It widens the stage columns and adds the production tables. Row level security is enabled and forced on those tables. The control database was not upgraded.

The laundry API on `127.0.0.1:18082` walked two existing orders to `READY_FOR_COLLECTION`:

- `LD-7B77A286`, garment `0e139bd7-114e-4068-b9ed-744ca3425fd9`, tag `LD-7B77A286-01`, dry clean. The balance stayed 1050 / 50 / 0 / 1050 cents.
- `LD-9584F748`, garments `d35fd178-4341-4c27-8978-7873d761576e` and `3bb559c5-f1e2-47c0-b2d4-24621ca5650a`, tags `-01` and `-02`, wash and fold. Tags and money were unchanged.

`LD-4F3A07CA` was not walked. A separate race order received one accepted sort and one 409 from two concurrent sort requests.

`ai_pos_app` is `LOGIN`, `NOSUPERUSER`, and `NOBYPASSRLS`. A query with no tenant context returned no stage events. Laundry-a saw its own events. Grocery-b saw none. A cross-tenant insert failed with SQLSTATE 42501.

Pytest: `tests/test_laundry_production.py`, `tests/test_laundry_orders.py`, and `tests/test_laundry_catalog.py` — 17 passed. The production file covers allowed and forbidden moves, duplicate and unknown tags, capacity, a machine fault and reassignment, QC failure and a second inspection, an incident hold with no refund, a cashier and a wrong-branch sorter, a rejected `laundry_stage` sync entity, and a duplicate packing scan.

## Register

The acceptance preview at `http://127.0.0.1:1421` was unlocked and opened Laundry. The stations shown were Dashboard, Order intake, Scan garment, Sorting, Production, Machines, Quality, Rework, Packing, Ready orders, Incidents, Order lookup, and Shift summary. The board loaded from the API: received today 7, awaiting sort 5, processing 1, batches 0, cycles 0, QC 0, rework 0, packing 0, ready 2, overdue 0, incidents 0.

The native acceptance process was started with `tauri.laundry-acceptance.conf.json`:

- Identifier `com.axizpos.laundry.acceptance`
- Product name AxizPOS Laundry Acceptance
- PID 13780
- Path `D:\Work\ai-pos\apps\desktop\src-tauri\target\debug\ai-pos-desktop.exe`
- First window title `AxizPOS Laundry Acceptance`
- First window handle 1117396

That window uses its own webview data and the acceptance URL `http://127.0.0.1:1421`. The signed-in floor walk above is the acceptance preview in the browser, not a click-through of the fresh native webview. The installed `com.aipos.desktop` register was not driven.

## Business Pro

`http://127.0.0.1:5174/laundry/production` showed the same board counts. `/laundry/workflows` listed `DRY_CLEAN`, `PRESS`, `WASH_FOLD`, and `WASH_IRON` with their full stage chains. The navigation also exposes batches, machines, quality, incidents, and the production report.

## Limitations

- The native window was identified and launched. Its fresh webview was not signed in and clicked through sorting, a machine cycle, QC, rework, an incident, and packing. Those paths passed in the API proof and in pytest.
- The register sorting action sends the configured category `mixed`. The server still rejects an unknown category.
- The register machine action uses the first available compatible machine and a weight the operator types.
- Pause is not a stage.
- Production mutations stay disabled offline. There is no queued stage transition.
- An incident does not create a refund.
- Tag printing remains the existing browser and QR path. No thermal printer was attached.
- The acceptance tenant currency remains USD.

## Exit

**Backend production engine:** COMPLETE WITH LIMITATIONS

**Windows POS production operations:** PASSED WITH LIMITATIONS

**Business Pro management:** PASSED WITH LIMITATIONS

**Security and data integrity:** PASSED WITH LIMITATIONS

**Overall Laundry Phase 3:** COMPLETE WITH LIMITATIONS
