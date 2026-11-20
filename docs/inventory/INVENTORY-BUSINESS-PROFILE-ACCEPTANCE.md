# Inventory business-profile acceptance

Date: 20 November 2026. Seven tenants were created with `python -m app.tenancy.cli create` on a disposable Postgres 16 at `127.0.0.1:55466`. The control database and the operational database were new. The acceptance database was not migrated and was not given these tenants. The disposable container was removed after the checks.

Each tenant completed onboarding, received one branch, created one product, and cancelled a one-line purchase order. Opening quantities stayed at 4, or 400 grams for the weighed grocery item. A second branch returned 409, "This plan includes 1 branches. Existing records stay available." That is the trial plan limit. Two-branch stock movement was not repeated here. It was already exercised on the acceptance tenant.

| Profile | What was verified | Result |
|---|---|---|
| Grocery | Preset includes weighed goods and FEFO. Serial tracking is off and the serial API returned 403. Product PLU `445577`, weighed, on-hand 400 grams. A pharmacy payload was not stored. | PASSED WITH LIMITATIONS |
| Fashion | Season `SS26`, collection `Closure`, and gender `women` were stored. FEFO and serial tracking are off in the preset. The variant matrix was not generated. | PASSED WITH LIMITATIONS |
| Electronics | Model `X100` was stored. Serial tracking is on. FEFO was rejected with 422, "Expiry-first stock (FEFO) does not fit a Electronics business." A pack other than piece was not created. | PASSED WITH LIMITATIONS |
| Restaurant | Product create and purchase cancel succeeded. The preset has recipes, modifiers, open orders, and kitchen display. FEFO is not in that preset. Pharmacy and serial APIs are off. | PASSED WITH LIMITATIONS |
| Cafe | Same purchasing and restriction result as restaurant. FEFO is not in the cafe preset. | PASSED WITH LIMITATIONS |
| Quick service | Same purchasing and restriction result as restaurant. FEFO is not in the quick-service preset. | PASSED WITH LIMITATIONS |
| Pharmacy | On the existing `inv-pharm` tenant, a prescription product cannot be marked for offline sale. A medicine receipt requires a manufacturer lot and expiry. An unreleased lot cannot be released by an admin. Quarantine and recall left the quantity unchanged. An appointed pharmacist released a separate lot. The tenant has one branch, so a transfer was not posted. | PASSED WITH LIMITATIONS |

Food-service FEFO remains available in the compatible module set. It is not switched on by the restaurant, cafe, or quick-service preset. This run did not switch it on.

Evidence: `acceptance/inventory/evidence/final-closure/profiles.json`. The pharmacy lot, quarantine, recall, and pharmacist release on the existing acceptance tenant are in `pharmacy-and-roles.json`, `governance.json`, and `pharmacist-release.json`.
