# Stage 1.2.4 evidence index

Windows form screenshots were not captured in this session. The acceptance register is not running, and the installed AI POS register was left untouched. Files already in this folder from the earlier attempt are listed as prior-session artifacts and are not a pass for this stage.

| Scenario | Filename | Viewport | Role | Tenant | Outcome |
|---|---|---|---|---|---|
| Process and connection identity | process-identity.json | n/a | n/a | inv-accept | Recorded |
| Persisted oats row, stock, images | database-oats.json | n/a | database owner, read only | grocery tenant 106cd7bd-87e6-43ca-9ec7-6853f7d936ce | Recorded |
| List, detail, stock, duplicates, category permission | api-verify.json | n/a | Floor Manager and catalog admin | inv-accept | Recorded |
| Product create form | not captured | n/a | Floor Manager | inv-accept | Not captured — acceptance register not open |
| Completed product creation | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Product list | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Product details | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Edit and save | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Archive result | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Duplicate SKU rejection | api-verify.json | n/a | Floor Manager | inv-accept | API 409. No new Windows screenshot |
| Duplicate barcode rejection | api-verify.json | n/a | Floor Manager | inv-accept | API 409. No new Windows screenshot |
| Image upload | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Saved gallery | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Gallery editing | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Dynamic specifications | not captured | n/a | Floor Manager | inv-accept | Not captured |
| SKU and barcode generation | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Dropdown search | not captured | n/a | Floor Manager | inv-accept | Not captured |
| Inline creation permissions | api-verify.json | n/a | Floor Manager and catalog admin | inv-accept | API only. No Windows screenshot |
| Stock-list authorization | auth-probe.txt and api-verify.json | n/a | device, Floor Manager, cashier | inv-accept | Prior device 403 retained. Manager retest HTTP 200. Device key on disk now returns 401 |
| 1024×768 | not captured | 1024×768 | n/a | n/a | Not opened |
| 1280×800 | not captured | 1280×800 | n/a | n/a | Not opened |
| 1366×768 | not captured | 1366×768 | n/a | n/a | Not opened |
| 1920×1080 | not captured | 1920×1080 | n/a | n/a | Not opened |

Prior-session image files remain on disk (`01` through `06`, `08` through `14`, and the `fixtures` directory). They were not recaptured and are not used as a pass.
