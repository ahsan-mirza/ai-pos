# O4 offline eligibility

Readiness of the product catalogue is not readiness of every tender. `checkout.ts` `chargeGate` still runs first: a server-reported subscription block stops the sale, a stale lease stops it unless the permanent entitlement is valid, and `blockPharmacyOfflineSale` stops a pharmacy medicine sale while offline.

| Operation | Offline | Rule in the current code |
| --- | --- | --- |
| Cash sale of a non-medicine product | Allowed when the gate above passes | `tenders.ts` cash branch. Cash received must cover the total. Short cash returns "Enter the cash received." Change is `received - total`. The queued tender is not a server acknowledgement |
| Card on an integrated terminal | Blocked until the provider intent is `PAID` | `tenders.ts` card branch. Declined, expired, cancelled, or missing intents do not produce a tender. A manager `manual_override` is the existing exception and is audited in `sale_service.py` `_audit_manual_card` |
| Card with no integrated terminal | The existing manual tender, not an offline authorisation | The tender has no `payment_intent_id`. O4 does not add an approval code |
| QR | Blocked until the QR intent is `PAID` | `tenders.ts` qr branch. A displayed code is not a completed payment |
| Pay-later | Blocked until the pay-later intent is `PAID` | `tenders.ts` bnpl branch |
| Bank transfer | Reference only | `tenders.ts` requires a non-empty reference. The reference is not proof the bank settled |
| Cheque | Reference only | Number, bank, and date are captured on the tender. Not a clearance |
| Pharmacy medicine | Blocked | `PHARMACY_OFFLINE_SALE` in `checkout.ts`. A downloaded catalogue does not bypass it |
| Serial or IMEI selection | Not authoritative | `serials.rs` can show a serial already queued on this register as `taken`. It does not reserve that serial against another till. The server checks it when the sale is applied |
| Customer lookup | Optional | `customers.rs` search uses the last cache. A sale without a customer does not need it |
| Promotion | Last fetched list only | `promotions.ts` `loadPromotions`. A disabled promotion is not removed on a disconnected till until that cache is refreshed |
| Entitlement | Unchanged from O2 | Valid permanent entitlement ignores a stale lease. Missing entitlement on a legacy file still uses the lease. A bad signature or a server hold blocks selling |

A locally queued cash sale remains queued until `flushSync` reports it synced. `submitCharge` returns `queued` when the batch is not yet `synced`.
