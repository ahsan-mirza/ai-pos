# Final-closure evidence

Date: 20 November 2026. API checks used `127.0.0.1:18081` or a disposable API on `127.0.0.1:18082`. The acceptance database volume is published on `127.0.0.1:55733`. The disposable profile container was removed. Screen captures are from the acceptance register only, PID 24440, title `AxizPOS Inventory Acceptance`. No passwords or tokens are stored here.

| Scenario | File | Result |
|---|---|---|
| Three-line purchase draft, edit, place, partial receipt, over-receipt, full receipt, repeat receipt, and cancel | workflows.json | Totals 1000 then 1300. Over-receipt 422. Cancel did not change stock. Oats stayed at 2. INV-TIN stayed at 7. |
| Three-line transfer, insufficient stock, ship, branch refusal, admin receive, and cancel | workflows.json | Source 12, 10, and 9. Destination 2 each. Insufficient transfer left the reservation at 2. |
| Categories, brands, units, price lists, price changes, batches, serials, replenishment | workflows.json | Store-bound writes that the API forbids returned 403. Grocery serials returned 403. |
| Stock count create, line, and cancel | stock-count.json | Status CANCELLED. On-hand stayed 12. |
| Seven profile tenants | profiles.json | Each profile initialized. Electronics FEFO returned 422. A second branch returned 409 because the trial allows one branch. |
| Cashier portal sign-in and missing terminal token | profiles.json | Cashier 403. Missing token 401. Store Manager create 409 because the trial allows two staff accounts. |
| Pharmacy lot, quarantine, and recall | pharmacy-and-roles.json | Offline prescription 422. Missing lot 422. Lot received unreleased. Admin release 403. Quarantine and recall left quantity at 4. Oats stayed at 2. |
| Pharmacist appointment and release | governance.json, pharmacist-release.json | Officers confirmed. Pharmacist authorized. Admin release 403. Pharmacist release 200, status RELEASED. |
| Store Manager branch and catalog | pharmacy-and-roles.json | Create 201. Other-branch adjustment 403. Category create 403. |
| Cashier PIN and stock | acceptance API after the seeded PIN restore | PIN 200. Stock 403. |
| Inventory screens at four sizes | products-*.png, purchase-orders-*.png, transfers-*.png, stock-counts-*.png, products-1024x768-table.png | Acceptance window PID 24440 only. At 1024×768 the section buttons wrap and the product table is reached by scrolling. |
| Windows browse and saved gallery | gallery.json, browse-three-photos.png, saved-gallery-reopened.png | The Open dialog owner was the acceptance window. Three images were stored. Reorder and remove persisted after the editor was closed and opened again. |
| Destination receipt, expiry, and revoked device | blocker-checks.json | Store B manager received the transfer. Store A Floor Manager received 403. Repeat receive returned 422. Expired token, invalid credentials, and a revoked device key returned 401. Oats stayed at 2. |
| Pharmacist self-approval | blocker-checks.json | The requesting officer received 403, `separation_of_duties`. The other officer rejected the appointment. |
| Drag-and-drop | product-form-drop-target.png | The photo control was open on PID 31216. A JPEG aimed at that webview was not added. |
