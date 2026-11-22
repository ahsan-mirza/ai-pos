# Laundry Phase 3.2 native POS UX acceptance

The laundry floor now scrolls inside the register shell, and the native acceptance window is a real acceptance build pointed at the disposable API. Order IDs, garment IDs, tags, prices, payments, balances, and production events were not changed. No developer, inventory, or production database was migrated. Nothing was deployed.

## Layout root cause

`RegisterShell` is a full-window column with `overflow: hidden`. The page row is `flex-1 min-h-0`, and the status bar is a sibling under that row. Checkout scrolls because `PageFrame` gives its main region `min-h-0 flex-1 overflow-y-auto`.

Laundry was rendered directly in that row as a section with only `min-w-0`. The section grew with the form, the shell clipped it, and the status bar could sit over the last controls. Adding `overflow-y-auto` on an unconstrained child does not scroll.

The laundry section is now a column that fills the row: header and station navigation stay `shrink-0`, and the work area is `data-laundry-scroll` with `min-h-0 flex-1 overflow-y-auto overflow-x-hidden`. Page Up, Page Down, Home, and End move that region when focus is not in an input, so a scanner field is not stolen. The status bar stays outside the scrolling region.

## What changed on the register

Station navigation is a compact bar. Daily operations, Production, and Management stay grouped. Below the large breakpoint the stations collapse to one menu. Pending counts stay on the production stations. A station the signed-in role cannot open is still hidden.

Primary actions stay AxizPOS orange and at least 48px high. Other controls are at least 44px, with a visible focus ring. Scan Garment uses two columns on a wide screen: tag entry on the left, the server garment on the right. A READY garment says its production path is complete. The screen does not invent a next stage. A 403 is titled as not permitted and is not retried.

Laundry Settings is ten read-only cards: General, Operating modes, Workflow templates, Service configuration, Production stations, Machines, Tags and labels, Quality rules, Notifications, and Permissions. Business Pro remains the editor for workflows, machines, and catalog rates. A refused settings read is shown on the page.

The native shell keeps the cashier token in the register process, not in the page. The floor treats that unlocked shell as signed in. The browser preview still requires the in-memory token. A reachable API is not treated as a signed-in cashier.

The acceptance binary now has a laundry profile. `ACCEPTANCE_PROFILE=laundry` bakes identifier `com.axizpos.laundry.acceptance` and API `http://127.0.0.1:18082`. The register path whitelist includes `/api/v1/laundry`. Before that, the native dashboard could reach the shell and still reject every laundry call as not allowed from the register. The browser preview never used that whitelist.

## Native window

The acceptance executable was built with the laundry profile and launched from `apps/desktop`:

- Identifier `com.axizpos.laundry.acceptance`
- Path `D:\Work\ai-pos\apps\desktop\src-tauri\target\debug\ai-pos-desktop.exe`
- Latest process PID 44088, window handle 1053738, title `AxizPOS Laundry Acceptance`
- Diagnostics guard passed
- API `http://127.0.0.1:18082`
- Data directory `C:\Users\ahsan\AppData\Roaming\com.axizpos.laundry.acceptance`
- SQLite `...\tenants\laundry-a\ai-pos.db`
- Activation source `activation`

The window started on Activate this register. It was activated as store code `laundry-a`, Branch A, register `LDACC32` (Laundry acceptance register). That is a new register on the disposable tenant so the existing preview device token was not rotated. The one-time key was not recorded.

PIN unlock used the acceptance Laundry Admin. The register opened the checkout shell with Laundry Admin, Super Admin, and footer Laundry Tenant A. The same session was still signed in after the whitelist rebuild.

The first native laundry screen, before the whitelist fix, showed the grouped stations and rejected the board because the laundry paths were not allowed from the register. After the fix, checkout rendered again. Further clicks in that webview left the client area white until a reload restored checkout. The station-by-station native walk, the four native viewport sizes, and native Page Up / Page Down were not completed. The window was minimized after that. The installed register was not used.

## Browser preview, kept separate

`http://127.0.0.1:1421` is the Vite preview, not the native webview. This tab had the Laundry Admin profile and no access token. The dashboard said the window is not signed in, and the board refusal was request `06145097dd9e4862a77746b3871807ef`: "This action is not permitted" / "This action requires a signed-in user." Retry was not offered for that refusal.

The scroll region was measured there:

- At 1024×768, scroll height 433 and client height 183. Scroll position moved from 0 to 165, and the end position covered the last content. The last content sat above the footer. Scroll width equalled client width.
- At 1280×800 and 1366×768 the region overflowed vertically and did not overflow horizontally. Ready Orders stayed inside the viewport at 44px.
- At 1920×1080 the short unsigned dashboard fitted the height. Station controls were 44px and quick actions 48px. Ready Orders remained inside the viewport. There was no horizontal overflow.

Laundry Settings showed all ten cards, and the refused settings read was written on the page instead of an empty panel.

## Live data

The disposable board was read after the UI work and was not written by this phase:

- Received today 7
- Awaiting sorting 5
- Processing 1
- Ready orders 2
- Active batches, machine cycles, quality, rework, packing, overdue, and open incidents 0
- Garments on the board 9

`LD-7B77A286`, `LD-9584F748`, and `LD-4F3A07CA` were not updated. No substitute order was created.

## Tests

- Desktop vitest `src/features/laundry`: 9 passed
- Rust `retail::tests`: 2 passed, including the laundry board and order paths and the rejection of `/api/v1/laundryx`
- Backend pytest for production, orders, and catalog: 17 passed

Desktop typecheck and the laundry eslint run were clean before the native launch.

## Business Pro

`/laundry/production` was not opened in this phase. The register and Business Pro still read the same board API. The counts above are that API. No routine floor action was added to Business Pro.

## White WebView

The native client area, including the sidebar, went white after a click and after the window was moved above another Chromium window. Reload restored Checkout, which is the in-memory default view.

`LaundryWorkspace` renders in the browser and in a static render test, so the laundry page is not an unconditional crash. Two separate faults match the blank window:

- React had no error boundary. A render throw unmounts `#root`, and the WebView paints an empty white document. `RegisterErrorBoundary` now keeps a recovery screen with the error and a reload action. `RegisterErrorBoundary.test.tsx` covers that state and a laundry render.
- Moving the acceptance window with the desktop compositor, while another GPU window was maximized behind it, left the WebView surface blank until the document reloaded. That host failure was not reproduced as a React route error. The station walk was not repeated on the desktop because earlier clicks landed in other applications.

The scan form was also mounted on every station because the scan branch fell through to `scanForm`. It now mounts only on Scan Garment.

## Limitations

- The native webview was activated and unlocked, then the interactive station walk stopped when the client area went white after a click. Reload restored checkout. Native scroll keys and the four native window sizes were not recorded.
- Packing reconciliation on screen still counts scans made in that visit. A repeat scan is rejected by the server.
- There is no server draft and no pause stage.
- Stage, batch, and machine changes stay disabled offline.
- An incident still does not create a refund.
- Order photos remain order evidence, not a photo on every garment line.

## Exit

**POS UI:** COMPLETE WITH LIMITATIONS

**Vertical scrolling:** PASSED WITH LIMITATIONS

**Native Windows acceptance:** PASSED WITH LIMITATIONS

**Touch interaction:** PASSED WITH LIMITATIONS

**Business Pro alignment:** NOT RUN

**Overall Phase 3.2:** COMPLETE WITH LIMITATIONS
