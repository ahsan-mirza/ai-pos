# Laundry order intake final acceptance

The New Order form now stays in normal document flow. Save Draft is gone. A live unlock on the disposable laundry register created one new order, and Order Lookup read that order back.

`LD-7B77A286`, `LD-9584F748`, `LD-9584A286`, and `LD-4F3A07CA` were not read, changed, or deleted. No production database was used. Nothing was deployed.

Overall: **PASSED WITH LIMITATIONS**.

## Layout defects

On the previous New Order screen, Special Instructions, Express, and Save Draft occupied the same visual area. The action row used `sticky bottom-0` inside the register's scrolling main, so those buttons stayed pinned over the fields as the form moved. Express was only the left cell of the two-column details grid, directly under the full-width instructions field, which put it in the sticky bar's path. The summary also used `xl:sticky`. Save Draft was disabled and sat beside a sentence that said a server draft is not supported.

There was no second scroll container on the form. The shell main (`overflow-y: auto`) is the only scroller. The footer sits outside that main. The overlap was the sticky action row, not a missing z-index.

## What changed

`apps/desktop/src/features/laundry/LaundryIntakePage.tsx`

- Details, Express, garments, photos, and deposit stay in normal flow. Nothing on the form is absolute, fixed, or sticky.
- Desktop widths from 1280px use two columns: the form on the left and one order summary on the right, top-aligned. Narrower widths stack the summary under the form.
- Express is its own row. The checkbox and label are one control, at least 44px tall. The surcharge sentence is separate and does not calculate an amount.
- The actions are a normal row under the form and summary: Create Laundry Order, Create and print receipt, and Cancel. They wrap. Create stays the orange primary button. Both create actions disable while a submit is in progress, and they stay disabled until the register is signed in or explicitly offline.
- Save Draft and the "server draft is not supported" sentence are removed. There is no draft service and no new draft store. An order that cannot reach the server, and that has no express flag and no deposit, can still be kept in the existing local queue. That queue is labelled as a pending local order, not a draft.

`apps/desktop/src/features/laundry/laundryNav.test.tsx` checks that the unsigned form has no Save Draft, no sticky action class, and a disabled Create Laundry Order.

No API, catalogue, tax, payment-provider, inventory, or offline sync file was edited. Retail Checkout was not edited.

## Authentication

Browser preview `http://127.0.0.1:1421`, talking to the disposable laundry API on `127.0.0.1:18082`.

Before unlock, the screen showed Unlock register. Create Laundry Order and Create and print receipt were disabled. No laundry order request was sent.

The unlock pad listed Laundry Admin. The acceptance PIN was entered on that pad. The overlay closed. The session stored in this window is online and the cashier name is Laundry Admin. `localStorage` has the cashier profile and does not contain an access token. Customers and the laundry service list loaded only after that unlock. Create Laundry Order became enabled.

A 401 is still an authentication failure. A different 403 is still a permission denial. No token was invented.

## Order created

One order on the disposable laundry tenant:

| Field | Value |
| --- | --- |
| Code | `LD-4A5DAFD6` |
| Customer | Walk-in Customer |
| Branch | Branch A |
| Piece line | Shirt, Dry clean shirt, quantity 2 |
| Weight line | Bedsheet, Wash and fold, gross 2500 g, tare 100 g |
| Production | `TAGGED` |
| Payment | `PARTIAL` |
| Server total | 46.20 |
| Server tax | 2.20 |
| Deposit | 5.00 |
| Balance | 41.20 |
| Accepted piece rate | 1000 cents at 500 bps |
| Stored rows | 1 garment, 1 bag, 2 tags |

The tags `LD-4A5DAFD6-01` and `LD-4A5DAFD6-02` are active. The intake receipt text rendered on the page, and Print tag, Print intake receipt, and Print payment receipt were available. The operating-system print dialog was not opened.

While the request was in flight the button read Creating and was disabled, and the print action was disabled with it. The database has one row for this code.

Order Lookup was opened at `#/laundry/lookup`, the code was entered, and the same code, customer, branch, payment status, balance, garment, and tags came back.

The deposit is the existing laundry deposit record. No payment provider was called.

## Viewports

Measured in the preview. Express did not overlap Special Instructions. Create Laundry Order stayed above the footer after scrolling to the end. The document did not scroll sideways. One element scrolled: the shell main.

| Viewport | Result |
| --- | --- |
| 1024×768 | Summary stacked. Express 44px. No overlap. Actions above the footer |
| 1280×800 | Summary beside the form. No overlap. Actions above the footer |
| 1366×768 | Summary beside the form. No overlap. Actions above the footer |
| 1920×1080 | Summary beside the form. No overlap. Actions above the footer |
| 125% (1093×614, dpr 1.25) | Summary stacked. No overlap. No clipped Express or instructions |
| 150% (911×512, dpr 1.5) | Summary stacked. No overlap. No clipped fields |
| 200% (683×384, dpr 2) | Summary stacked. No overlap. No clipped fields |

The device-metrics override was cleared.

## Native Windows

**NOT RUN.** A dedicated acceptance window was not launched in this pass. The browser preview is not native evidence. The installed register was not used, and no global click or keystroke was sent.

## Tests

`pnpm exec vitest run src/features/laundry/laundryNav.test.tsx src/features/laundry/floorUx.test.tsx`

10 passed, 0 failed.

## Confirmation

- Retail Checkout is unchanged and is still not mounted for a laundry profile.
- Laundry still opens on Orders. New Order is still the default.
- Production routes, the service catalogue, tax calculation, and the order API were not replaced.
- The named acceptance orders were not read or modified.
- The new order exists only on the disposable laundry acceptance database.
- No production deployment was made.
