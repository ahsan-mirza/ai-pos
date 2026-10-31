# Company Console

There is no new console page and no second subscription engine.

`uae_einvoicing` is a capability labelled "UAE e-Invoicing". It is eligible on every current business profile and is outside every starter preset. `ensure_module_addons` inserts `billing_addons.code = uae_einvoicing` with `monthly_fils = 0` and the description "UAE e-invoicing for in-scope business and government sales. The price is set in the console."

Operators set the price in fils on the existing Add-ons screen. Purchase, expiry, renewal, suspension, and reactivation stay on the existing subscription items. `publish_purchased` is what turns the portal menu and the API writes on.

Historical invoice rows are not deleted when the subscription ends. New outbox writes and retries require the capability. See `TENANT_SECURITY.md` for the portal visibility gap after expiry.
