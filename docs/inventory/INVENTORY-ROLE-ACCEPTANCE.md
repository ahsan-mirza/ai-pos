# Inventory role acceptance

Date: 20 November 2026. No permission was added to make a check pass.

## Acceptance tenant

The Floor Manager signed in and created the disposable products, purchase orders, receipts, and the transfer. Category, brand, and price-list creates returned 403. Unit create was allowed. The catalog admin, who is not bound to a store, created and deleted a category, a subcategory, and a brand, created a price list, and received the transfer at Store B. The Floor Manager's receive at Store B returned 403.

The earlier cashier PIN login returned 200. Stock and stock adjustment returned 403. That check was not repeated.

## Disposable grocery tenant

The system roles present were Super Admin, Store Manager, Cashier, Technician, and Demo Explorer. There is no system role named Floor Manager, Inventory Clerk, Procurement, Catalog administrator, Pharmacist, or Pharmacy governance officer. Floor Manager on the acceptance tenant is the custom role Acceptance Floor. Catalog administration is the unbound Super Admin.

The cashier account has no portal access. Password sign-in returned 403, "This account cannot sign in to the web portal." The adjustment call was therefore not reached. A missing terminal token on sync returned 401, "A valid terminal token is required."

Creating a Store Manager returned 409, "This plan includes 2 staff accounts. Existing records stay available." The trial already held the admin and the cashier. The plan was not enlarged.

The admin session still read settings after the other calls. There is no logout route. Token expiry is 30 minutes and was not waited out.

## Pharmacist and governance

A pharmacist appointment is not a role permission. The pharmacy product stored offline policy `BLOCK`. The officer nomination, pharmacist appointment, lot release, recall, and quarantine flow was not run on the disposable pharmacy tenant. Account appointment would not prove a natural person's identity or a licence.

## Later the same day

The seeded cashier PIN was restored and PIN login returned 200. Stock then returned 403, code `forbidden`. A Store Manager was created from the existing Store Manager role and bound to Store A. Sign-in returned 200. An adjustment at Store B returned 403, "You can only work with your own store's stock." A category create returned 403.

On the pharmacy tenant, two officers were nominated and confirmed. They appointed a pharmacist. The pharmacist authorization read `authorized: true`. The admin read `authorized: false`. The admin release returned 403, `pharmacist_required`. The appointed pharmacist released a separate lot and its status became `RELEASED`. That appointment is an account record. It is not proof of a natural person's identity or a licence.

Inventory Clerk and Procurement are still not system roles. The register lock clears the token held in the window. There is no server logout route, and one was not added because the access token is a stateless JWT. An already expired token returned 401, `invalid_token`. A disposable register key returned 200, and the same key returned 401, `device_revoked`, after revoke. The acceptance register's device was not revoked.

A Store Manager bound to Store B received a shipped transfer. The Floor Manager bound to Store A received 403, `store_scope`. The officer who requested a pharmacist appointment received 403, `separation_of_duties`. The other officer rejected it. That appointment is an account record, not a licence or identity check.

## Status

Role acceptance: **PASSED WITH LIMITATIONS**.
