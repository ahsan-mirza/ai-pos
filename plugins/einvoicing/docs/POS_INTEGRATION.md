# POS integration

Checkout is unchanged for a customer without a TRN.

When the add-on is enabled and the selected customer has `trn_vat_number`:

- The charge still uses the existing local sale and the existing sync queue.
- The receipt text adds one sentence: the UAE e-invoice is pending, and the receipt is not provider acceptance.
- The POS does not call an ASP and does not display `ACCEPTED` from local storage.

When the plugin database table is missing, the API is down, or the ASP (including the mock) is down, checkout still completes. A queued offline sale syncs later through `POST /api/v1/sync/push`. The outbox row is written then, not from the register.

Buyer details required for an in-scope invoice are the existing customer name and 15-digit TRN. Ordinary consumer checkout does not ask for a TRN. Government buyers are not detected on the POS; they are customer ids stored in e-invoicing settings.
