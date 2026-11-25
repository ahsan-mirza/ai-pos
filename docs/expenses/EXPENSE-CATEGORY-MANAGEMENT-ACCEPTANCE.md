# Expense categories — acceptance

Status: **PASSED WITH LIMITATIONS**

`expense_categories` holds the tenant's expense types. The original nine codes and names are seeded and are not renamed. Existing expenses keep their category code. The first read links that code to the seeded row when the code still matches.

POS and Business Pro load `GET /api/v1/expenses/categories`. The category control searches those rows. When nothing matches, **+ Add Expense Type** posts `POST /api/v1/expenses/categories` and selects the returned id. The other expense fields stay on the form. A repeated name returns the existing category. A blank name is rejected. Deactivating a category removes it from the list for new expenses. An expense already recorded with that category still shows the name.

`expenses:manage` is required. A cashier PIN is still rejected with “You do not have permission for this action.”

Categories are tenant-wide. There is no branch-only category, because the previous list was not branch-specific.

Automated: `tests/test_expenses.py::test_custom_category_and_compressed_bill` (create, duplicate name, blank name, deactivate, historical name). Desktop typecheck passed. A live pair of windows was not used to watch one category appear in the other app. Both apps call the same route.
