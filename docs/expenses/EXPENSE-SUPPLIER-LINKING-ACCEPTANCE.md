# Supplier-linked expenses — acceptance

Status: **PASSED WITH LIMITATIONS**

`expenses.supplier_id` references `suppliers`. Paid to stays optional text. A blank Paid to is filled with the supplier name. A blank tax-invoice TRN is filled from the supplier TRN. The expense does not create an accounts-payable bill.

POS and Business Pro search suppliers by name, code, phone, and TRN, and can clear the selection. A user with `payables:manage` or `portal:inventory_manage` can add a supplier from the expense form through `POST /api/v1/expenses/suppliers`. Anyone else with only `expenses:manage` can select a supplier and cannot create one.

The expense list accepts `supplier_id`. The POS list has a supplier filter. Business Pro's supplier statement includes an Expenses section for the current year when the signed-in user can read expenses. That section is hidden when the expenses request is refused.

Automated: `tests/test_expenses.py::test_expense_records_the_supplier_without_opening_a_bill`. Inactive and unknown suppliers return 422. A second tenant was not opened in this pass.
