# Stage 3F operations handbook

Only workflows that exist in the current software are described. Pending decisions are marked. This handbook is not a regulatory approval.

## 1. Pharmacy tenant prerequisites

The tenant needs the pharmacy catalogue capability and FEFO. Turning the capability on is a tenant configuration change. Do not enable it for every tenant. Grocery and the other profiles do not follow pharmacy lot rules.

The API must be reachable for a pharmacy sale. The register blocks a stocked sale while the pharmacy capability is on and the API cannot be reached. That sale is not queued and does not take an invoice number.

## 2. Medicine product onboarding

Create the product in the pharmacy catalogue. The stored fields include generic name, manufacturer, dispensing class, dosage form, route, strength, pack label, units per pack, base and selling units, price control, ingredients, and the usual product price, tax, and active flag. Archive uses the existing product active flag. Veterinary products stay off until a later licence exists. Prescriptions, controlled-drug registers, and insurance claims are not part of this product form.

## 3. Supplier receiving

Receive the medicine on a goods receipt. Enter the manufacturer lot, expiry, quantity, and cost. Manufacture date is stored when it is entered and must not be after the expiry. The receipt number is the document number. The manufacturer lot is a separate field. The new layer is `UNRELEASED`. Receiving does not make the medicine saleable. On-hand increases through the stock movement. A receipt event is written.

## 4. Manufacturer lot management

A layer holds the manufacturer lot, expiry, manufacture date when present, cost, and status. Status values in use are `UNRELEASED`, `RELEASED`, `QUARANTINED`, `RECALLED`, and `SUPPLIER_RETURN`. `DAMAGED` is stored and rejected for sale and release, but no screen sets it. See the damaged-stock decision. That decision is pending.

## 5. Pharmacist nomination and authorization

A governance officer is nominated and confirmed by a different officer. A pharmacist appointment is requested and approved by a different authorized officer. The same account cannot approve itself. Super Admin synchronization does not grant appointment authority. Revocation removes the ability to release or clear. History remains on the authorization and audit rows.

These checks separate accounts. They do not prove two natural persons, and they do not check a pharmacist licence.

## 6. Lot release

An appointed pharmacist releases an eligible layer with a reason and an explicit confirmation. Release is rejected for recalled, damaged, expired, empty, and ineligible layers. The update is the existing lot transaction. An audit event is written. A manager who is not an appointed pharmacist cannot release.

## 7. Quarantine

Quarantine requires a reason. It writes a quarantine event and an audit row. It does not change quantity. A quarantined layer cannot be sold. A recalled layer cannot be quarantined into a clearable state.

## 8. Clearance

An appointed pharmacist can clear a quarantine that is still eligible. A recalled lot cannot be cleared. An expired lot cannot be released. Clearance does not change quantity.

## 9. Recall

Open a recall against the manufacturer lot. Remaining matching layers, including descendant transfer layers in the tenant, become `RECALLED`. Quantity is not changed. Sales that drew those layers can be listed. Sale and release of a recalled layer are rejected. Closing a recall uses the existing recall status change. The software does not notify a regulator or a customer.

## 10. Pharmacy transfers

Ship only released, in-date source layers. The source allocation keeps the manufacturer lot, expiry, and cost. The destination layer is created `UNRELEASED`. An open recall follows the lot. Quantity cannot go negative. Non-medicine transfers do not gain a pharmacy layer.

## 11. Supplier returns

Return part or all of a layer. Each return writes a movement. A full return leaves the layer at zero and `SUPPLIER_RETURN`. A zero-quantity layer cannot be sold. A second return cannot deduct the same units again. History remains.

## 12. Pharmacy sales

The cashier does not pick a lot. The server allocates released, in-date layers, earliest expiry first. If one line cannot be filled, the whole sale rolls back. A replay of the same sale id does not draw stock again.

## 13. Offline checkout rejection

With the pharmacy capability on, a stocked sale is refused while the API is unreachable. The local invoice series does not advance. A cached PIN unlock does not become an online session. When the API is reachable again, a cashier signs in online before the next sale.

## 14. Online session recovery

After the API returns, the header can show connection restored while the session is still offline. If jobs are pending, the label includes that count. An empty queue does not show the register as online. A failed sync batch, with nothing still pending, shows a sync-failed label. Those labels are in the register code. They were not recaptured on a window in this stage.

## 15. Stock and lot audit history

Lot events are append-only. Release, quarantine, recall, transfer, and supplier return write their events and audit rows. Customer return of a released medicine writes a quarantine event. Opening stock and sales write stock movements. Do not edit those rows in place.

## 16. Common errors

| Message or code | Meaning |
|---|---|
| `lot_unreleased` | The only stock has not been released. |
| `lot_expired` | The layer is past expiry. |
| `lot_quarantined` | The layer is on hold, including after a customer return. |
| `lot_recalled` | The lot is under recall. |
| `lot_damaged` | The layer is stored as damaged. Sale and release refuse it. |
| `pharmacist_required` | The caller is not an appointed pharmacist. |
| Offline pharmacy refusal | The API cannot be reached. The sale is not queued. |

## 17. Permission requirements

Catalogue and receiving use the existing inventory permissions and store scope. Release, quarantine clearance, and pharmacist appointment use the governance records. A store-scoped user cannot act for another store. The terminal device token authenticates the register's sale upload. The cashier session is separate.

## 18. Backup and recovery

Back up the operational database and the control database before a production change. Restore practice belongs on a disposable server. Application rollback is to redeploy the previous build and leave the pharmacy columns in place. Do not downgrade Alembic on a live tenant as an incident response.

## 19. Known limitations

- Damaged-stock policy is pending. Do not mark a layer `DAMAGED` from a new button.
- Licence and natural-person checks are not implemented.
- A customer return quarantines the whole released manufacturer layer, including units that stayed on the shelf. A pharmacist release is required before any of that layer can be sold again. There is no approved path that restocks a return straight to `RELEASED`.
- Recall does not send an external notice.
- PostgreSQL FEFO, release, and governance races passed on a disposable database in Stage 3F.1. Supplier-return, customer-return, and recall-versus-sale races were not run there. A fresh Windows pass of the header states was not run.
- No signed production installer was produced.

## 20. Escalation

Stock that will not release, a recall, a suspected cross-tenant read, or an invoice-number jump goes to the operator who owns the tenant database and to the pharmacy operations owner. Do not clear a recall or force a sale from the database. Do not enable pharmacy on a production tenant to reproduce a fault.
