# Final-release evidence index

Windows screenshots were not captured. The installed register stayed open, so the acceptance window was not driven.

| Scenario | Evidence | Role | Tenant | Viewport | Result |
|---|---|---|---|---|---|
| Reference oats and INV-TIN | stage-1.2.4/database-oats.json and follow-up.json | Floor Manager | inv-accept | n/a | Unchanged |
| Duplicate SKU | follow-up.json | Floor Manager | inv-accept | n/a | HTTP 409 |
| Two-line purchase order, then cancel | follow-up.json | Floor Manager | inv-accept | n/a | 201, then cancelled. Stock unchanged |
| Enrolled device product list and stock | follow-up.json | Device | inv-accept | n/a | 200 and 403 signed-in user |
| Cashier stock | follow-up.json | Cashier | inv-accept | n/a | 403 permission |
| Acceptance identity | acceptance-diagnostics.json on the acceptance profile | n/a | inv-accept | n/a | developer_env_loaded false |
| Product form, gallery, viewports | not captured | Floor Manager | inv-accept | not opened | Not captured |
| Categories, brands, models, units, pricing screens | not captured | n/a | n/a | not opened | Not captured |
| Multi-line transfer that moves stock | not run | n/a | n/a | n/a | Not run, because create reserves stock |
| Production installer and signature | not produced | n/a | n/a | n/a | Blocked, certificate required |
