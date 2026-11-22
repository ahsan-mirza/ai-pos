# Laundry POS shell and authentication acceptance

The laundry floor now uses the same register shell as Inventory. The grouped three-row station card is gone. A window with a visible cashier and no access token does not call the laundry board, and it does not paint an empty board as if the API had returned zeros.

No laundry order was created or updated. `LD-7B77A286`, `LD-9584F748`, and `LD-4F3A07CA` were not touched. Nothing was deployed.

## Root cause: missing header

`RegisterShell` already draws the sidebar once and `PageFrame` draws `HeaderBar` (language and theme) above the page. Inventory uses that frame. Laundry rendered its own full-height section directly in the shell row, so the shared header never mounted. The cashier, lock control, and module icons were still the shared sidebar.

Laundry now returns `PageFrame`, the same component Inventory uses. The cash-drawer action sits in that header. Branch, operator, role, session, API, and sync are no longer a second status grid. The sidebar keeps the cashier. The footer keeps activation, reachability, and sync as separate chips.

## Root cause: navigation

Station groups (`Daily operations`, `Production`, `Management`) were a laundry-only card. The row is now `AxizTabs`, the same underline tabs Inventory uses through `InventoryTabNavigation`. There is no second tab stylesheet. Active text uses the AxizPOS orange underline (`rgb(242, 106, 33)` in the preview). Tabs stay one row (`flex-nowrap`, 48px) and scroll inside the tab list when they overflow. The shell document does not scroll sideways.

The open station is the hash (`#/laundry/<station>`). A click pushes a history entry. Back and forward read `hashchange` and `popstate`. A station the role cannot open falls back to the first allowed station and is not left as a reachable route.

## Root cause: authentication

Two different facts were being treated as one session.

- The cashier profile can be restored after a refresh. The access token is memory-only. A name or role on screen is not a token.
- Laundry routes require a user principal. The API answers a terminal/device principal with HTTP 403 and the sentence "This action requires a signed-in user." That is not a role denial, and it is not proof that the API is down.

The browser called protected laundry and intake reads before a token existed. The shell also forwarded a laundry path with only the terminal key when `user_token` was empty. The floor then classified that 403 as "This action is not permitted" and still rendered "No priority exceptions" from an empty local list.

What changed:

- `registerSignedIn` is true only when this window holds an access token, or the native shell is in an online unlock (the token stays in the register process). An offline unlock has no user token.
- The dashboard, catalog reads, and intake prefetch do not start until that check passes.
- In the browser, `laundryCall` throws 401 before `fetch` when there is no token.
- In the native shell, `/api/v1/laundry` without a user token returns locally: 401 when the unlock is online, offline when the unlock is offline. The HTTP client is not started. An offline create can still queue. A missing token is not turned into a fake permission error.
- HTTP 401, and HTTP 403 whose message is "requires a signed-in user", stop further board retries and show Unlock register. The register is not locked out and the terminal activation record is not cleared.
- Any other HTTP 403 stays a permission denial. The session stays signed in.
- HTTP 404, 422, 5xx, and network failure stay separate. A 5xx title is not the server body; the body is kept in the support detail and in `console.error`.
- The request id from the API body or `X-Request-Id` is kept on the shell error and shown under Support reference.
- Dashboard metrics and "No priority exceptions" render only after a successful board response. A failed or skipped load has no zero-value cards.

Unlock uses the existing `PinUnlock` and `unlock` / `unlockSelected` path. The new session is written through the register `onUnlocked` handler. No token is written to `localStorage` or `sessionStorage`.

## Status indicators

On the acceptance preview, at the same time:

- Footer activation: Not activated
- Footer reachability: Online
- Page session: Unlock the register, because this window has no access token

Those three readings come from the terminal record, the API probe, and the in-memory token. They are not one combined string.

## Files changed

- `apps/desktop/src/features/laundry/LaundryWorkspace.tsx`
- `apps/desktop/src/features/laundry/LaundryIntakePage.tsx`
- `apps/desktop/src/features/laundry/diagnostics.ts`
- `apps/desktop/src/features/laundry/ui.tsx`
- `apps/desktop/src/features/laundry/shellScroll.ts`
- `apps/desktop/src/features/laundry/floorUx.test.tsx`
- `apps/desktop/src/App.tsx`
- `apps/desktop/src/components/shell/statusBar.ts`
- `apps/desktop/src-tauri/src/retail.rs`

## Routes and tabs

Existing stations only: Dashboard, Order Intake, Order Lookup, Scan Garment, Sorting, Production, Machines, Quality Control, Rework, Packing, Ready Orders, Incidents, Shift Summary, Laundry Settings. Visibility still comes from `visibleStations`.

## Tests

Desktop Vitest, 22 Nov 2026:

- `src/features/laundry` and `src/features/inventory/InventoryTabNavigation.test.tsx` and `src/components/shell/statusBar.test.ts`
- 4 files, 28 tests, 28 passed

Rust `retail::tests`: 4 passed, including the laundry path whitelist, the block when a laundry path has no user token, and request-id retention.

`tsc` reports no errors in the laundry files. It still reports existing errors in `RegisterErrorBoundary.tsx` and checkout tests. Those files were not part of this change.

## Preview measurements

Browser preview `http://127.0.0.1:1421`, acceptance laundry Vite, not the native WebView. The signed-in profile was visible and the access token was absent. Resource timing showed no `/api/v1/laundry` board request. The dashboard showed the unlock explanation and did not show priority or KPI numbers.

| Viewport | Document scroll width | Tab row | Tab height | Active tab |
| --- | --- | --- | --- | --- |
| 1024×768 | 1024 = client | nowrap, list scrolls 1356 > 906 | 48px | Order Intake via hash |
| 1280×800 | 1280 = client | nowrap, 1356 > 1162 | 48px | Order Intake |
| 1366×768 | 1366 = client | nowrap, 1356 > 1249 | 48px | Order Intake |
| 1920×1080 | 1920 = client | nowrap, row fits at 1834 | 48px | Dashboard after hash update |
| 1093×614, scale 1.25 | 1093 = client | nowrap, 1356 > 981 | 48px | 125% sized |
| 911×512, scale 1.5 | 911 = client | nowrap, 1356 > 799 | 48px | 150% sized |
| 960×540, scale 2 | 960 = client | nowrap, 1356 > 848 | 48px | 200% sized |

At 1024×768 the intake form scrolled inside `main` (scroll height 1548, client height 676). At the end of that scroll, Find order sat above the footer. The active underline color was `rgb(242, 106, 33)`. Inventory still opened on Stock with the same header and its own tab labels.

## Native Windows

**NOT RUN.** The Tauri acceptance window was not launched for this pass. The shell token guard is covered by the Rust unit test, not by a live WebView. Do not treat the Vite preview or Vitest as native acceptance.

## Limitations

- A successful PIN unlock was not completed in the preview. The unlock screen is the existing register PIN screen. This window had no cashier directory cards, and no PIN was entered. The authenticated board load after unlock was not observed live.
- Offline intake still needs services loaded from an earlier online session before a new draft can be queued. A missing token does not invent that catalog.
- Packing counts in the visit are still local until the server accepts them.
- Native viewport, zoom, and PIN acceptance remain **NOT RUN**.

## Exit

| Check | Status |
| --- | --- |
| Shared POS shell and header | PASSED |
| Single-row orange underline tabs | PASSED |
| No protected board call without a user token | PASSED |
| 401 / device-principal 403 / real 403 / 404 / 422 / 5xx / offline classification | PASSED |
| Empty board only after a successful load | PASSED |
| Activation, session, and reachability stay separate | PASSED |
| Inventory tab regression in the preview | PASSED |
| Live unlock then authenticated board | NOT RUN |
| Native Windows window | NOT RUN |
| Overall | PASSED WITH LIMITATIONS |
