# Laundry orders and checkout UX acceptance

A laundry business now opens on Orders inside the shared register shell. Retail Checkout is unchanged and is not mounted for a laundry profile. Laundry orders still use the existing laundry order API. No new order table, catalogue, or sale path was added.

No laundry order was created or updated. `LD-7B77A286`, `LD-9584F748`, and `LD-4F3A07CA` were not read or written. Nothing was migrated or deployed.

Overall: **PASSED WITH LIMITATIONS**.

## Profile navigation

| Profile | Sidebar entry | What opens |
| --- | --- | --- |
| Retail and other non-laundry profiles | Checkout | Existing `CheckoutPage`, cart, product sale, and sale API |
| Laundry | Orders | Existing `LaundryWorkspace` on the laundry hash |
| Food and beverage | Orders & Tables | Existing F&B orders view. That view id was not reused for laundry |

For `profile === "laundry"` the checkout sidebar item is labelled Orders and navigates to the laundry workspace. The extra Laundry sidebar item is hidden so the register does not show two entries for the same floor. A non-laundry profile that still has laundry permission keeps Checkout and the separate Laundry item.

The default laundry hash opens New Order (`#/laundry/intake`). An explicit station is kept. `#/laundry/dashboard` and `#/laundry/sorting` still resolve. Refresh on `#/laundry/sorting` stayed on Sorting.

## Shared components

- `RegisterShell` and `SidebarNav` for the sidebar.
- `PageFrame` and `HeaderBar` for the language, theme, and drawer actions.
- `AxizTabs` for both laundry rows. There is no second tab stylesheet and no pill or card tab.
- Existing station permissions from `visibleStations`. Production routes were not removed.

Primary row: Orders, Production, Services, Customers, Reports. Settings is the sidebar gear, which opens `#/laundry/settings`. It is not a tab on this row.

Orders row: New Order, Active Orders, Order Lookup, Ready for Collection. New Order is the default and is also a button on the other order screens when the user can create an order.

Production row, only the stations that role can already open: Scan Garment, Sorting, Production, Machines, Quality Control, Rework, Packing, Incidents, Shift Summary.

## Intake

New Order is the existing intake screen.

- Walk-in, drop-off, and pickup stay the existing order types.
- Customer lookup uses the existing customer list. This screen does not register a customer.
- Branch, promised completion, express, instructions, deposit, and discount stay on the existing form.
- Each line has a garment type and a separate laundry service. The same garment type can use a different service on another line.
- Piece lines use quantity. Kilogram lines use gross and tare. The catalogue supplies the service and its unit. Prices are not hardcoded.
- Tax and the order total are still calculated by the server. The summary says so before the order exists. After the server accepts the order, the summary shows the server total, tax, deposit, and balance.
- The submit button is **Create Laundry Order**. It is disabled while a submit is in progress. Validation still runs before a payload is built.
- Photos, tags, and the deposit field are the existing ones.

## Garment, service, and stock

| Kind | Examples | Where it lives |
| --- | --- | --- |
| Laundry service | Wash & Fold, Dry Clean, Ironing | Laundry catalogue. Selected on an order line |
| Garment type | Shirt, Abaya, Bedsheet | The item received. Not a service |
| Physical product | Detergent, packaging, garment covers | Existing Inventory. Not created by adding a service |

The Services row is a read of the existing catalogue: Laundry Services, Service Categories, Garment Types, and Service Pricing. Service templates have no register editor. The screen says they stay in Business Pro. Adding a service does not post a stock movement.

## Payment and production

Production status and payment status are shown as separate fields on the order list and after intake. The payment summary labels deposit paid, balance due, and payment status. A ready garment can still have a balance; the existing ready filter already keeps unpaid ready work out of the paid filter. The register does not mark an order paid except through the existing deposit and payment calls.

## What was not given a new screen

- Service template editing. Out of scope on this register.
- A new customer registration endpoint.
- A financial report builder. Reports opens the existing shift summary. Other laundry reports stay in Business Pro.
- A second stock ledger and any change to the offline sync batch.

## Files

- `apps/desktop/src/App.tsx` — laundry profile renders the laundry workspace and does not mount retail checkout.
- `apps/desktop/src/components/shell/SidebarNav.tsx` — laundry profile label and target.
- `apps/desktop/src/features/laundry/laundryNav.ts` — section model.
- `apps/desktop/src/features/laundry/laundryNav.test.tsx` — navigation and intake cases.
- `apps/desktop/src/features/laundry/LaundryWorkspace.tsx` — two tab rows and the existing stations.
- `apps/desktop/src/features/laundry/LaundryReferencePages.tsx` — read-only orders, catalogue, and customers.
- `apps/desktop/src/features/laundry/LaundryIntakePage.tsx` — garment/service copy and Create Laundry Order.
- `apps/desktop/src/features/laundry/ui.tsx` — shared underline rows and payment labels.

No API router, model, or migration was edited.

## Tests

`pnpm exec vitest run src/features/laundry/laundryNav.test.tsx src/features/laundry/floorUx.test.tsx`

9 passed, 0 failed.

Covered:

- Retail label stays Checkout. Laundry label is Orders. F&B Orders & Tables is unchanged.
- Primary labels and one underline row (`flex-nowrap`, `h-12`, orange underline class, no grouped card).
- Production station ids remain reachable under Production.
- Explicit dashboard, intake, and sorting hashes resolve. An empty hash opens intake.
- The same garment type on two lines with different services passes validation.
- A piece line and a kilogram line pass together. A missing customer and a bad quantity fail before a payload is built.
- Existing floor tests still separate a ready unpaid garment from a paid one, and still refuse a laundry call with no token before `fetch`.

## Preview

Browser preview at `http://127.0.0.1:1421`. Not the installed register.

- Sidebar says Orders. There is no Checkout button. Header language and theme controls are present. Footer shows Downtown Flagship · Laundry.
- Orders opens New Order. Production opens Scan, Sorting, Production, Machines, Quality Control, Rework, Packing, Incidents, and Shift Summary.
- Services shows the four catalogue tabs and the Business Pro note for templates and stock products. With no access token it does not call the catalogue.
- Loading `#/laundry/sorting` selects Production and Sorting.
- Inventory still opens Stock, Products, Pricing, and the product search. Returning to Orders keeps the sorting hash.
- No `/api/v1/laundry` or `/api/v1/sales` request was recorded while the window had no access token.
- Active tab underline measured `rgb(242, 106, 33)`. Tab rows are 48px, `flex-nowrap`, and `overflow-x: auto`.

| Viewport | Document scroll width | Tab rows | Form |
| --- | --- | --- | --- |
| 1024×768 | 1024 = 1024 | 48px, nowrap, no shell overflow | Main scrolls. At the end, Find order bottom 607 is above footer top 732. Create Laundry Order is 48px tall |
| 1280×800 | equal | 48px, nowrap, scroll width equals the row | Main overflow auto |
| 1366×768 | equal | 48px, nowrap | Main overflow auto |
| 1920×1080 | equal | 48px, nowrap, row 1834 = 1834 | Main overflow auto |
| 125% (1093×614, dpr 1.25) | 1093 = 1093 | 48px, nowrap | |
| 150% (911×512, dpr 1.5) | equal | 48px, nowrap | |
| 200% (960×540, dpr 2) | equal | 48px, nowrap | |

The device-metrics override was cleared after these checks.

## Native Windows

**NOT RUN.** The acceptance executable was not launched. The installed register was not used. No global click or keystroke was sent.

## Limitations

- Live PIN unlock was not performed. The preview had a cashier profile and no access token, so order create, catalogue rows, and customer rows were not loaded from the API.
- A disposable order was not created. The three named acceptance orders were not modified because no order request was sent.
- Service template editing and a full financial report remain in Business Pro.
- Customer registration was not added.

## Confirmation

- Retail `CheckoutPage` was not redesigned. A laundry profile does not mount it.
- Existing laundry order, deposit, tag, and production routes were not replaced.
- Existing order records were not modified.
- No production deployment was made.
