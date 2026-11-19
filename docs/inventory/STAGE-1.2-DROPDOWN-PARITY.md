# Stage 1.2 dropdown parity

Business Pro dropdowns are `Select` in `packages/ui/src/Select.tsx`. The product form reaches them through `SelectField`. The register uses the same `Select` through `CreatableLookupField` in `apps/desktop/src/features/inventory/creatableLookup.tsx`.

Status: `FORM PARITY IN PROGRESS`. The component is shared. On the rebuilt inventory register, the store-bound Floor Manager opened Category, typed `dry`, saw only Acceptance Dry Goods, and saw no Add action. Inline create for a tenant catalog admin was not clicked. Unit, supplier, and the other inventory screens do not use this field yet.

## Search

| Behaviour | Business Pro | Register |
|---|---|---|
| Search box inside the menu | On when `onCreate` is set, or when the list has more than eight options | Forced on for every `CreatableLookupField` |
| Match | Case-insensitive label match | Same component |
| Empty state | The shared menu's empty state | Same component |
| Keyboard | Arrow keys and Enter in the shared menu | Same component |
| Clear | An empty option such as "None" or "No model" | Same options |
| Remote search | Category, brand, and model lists are loaded, then filtered locally. Barcode and SKU uniqueness use a debounced product search | Lists are loaded, then filtered locally. Barcode uniqueness uses product search when a code is generated or left for auto-assign |

## Inline creation

Business Pro shows `+ Add` only when `onCreate` is passed. The product form passes it only when `catalogAdmin` is true: `Permission.PortalInventoryManage` and `user.store_id === null`.

The register uses the same gate: inventory manage, and the signed-in user is not bound to a store. A store manager can choose an existing category, sub-category, brand, or model. The add action stays hidden.

| Record | Create call | After create |
|---|---|---|
| Category | `POST /api/v1/categories` with the typed name | List reloads, the new id is selected, sub-category and model clear, specifications clear |
| Sub-category | `POST /api/v1/categories/{id}/sub-categories` | List reloads, the matching sub-category is selected, model and specifications clear |
| Brand | `POST /api/v1/brands` with `sub_category_ids` | Requires a sub-category. List reloads, the new brand is selected, model clears |
| Model | `POST /api/v1/product-models` with brand and sub-category | Requires both parents. List reloads, the new model is selected |

A failed create leaves the rest of the product form as it was and shows the API message. Gender and VAT stay ordinary controlled selects. Specification values can be added inside the specification control. That adds a value on the product, not a new category record.

## Not yet on the shared lookup

Unit, supplier, and the other inventory screens still use their existing register controls. They do not all go through `CreatableLookupField`.
