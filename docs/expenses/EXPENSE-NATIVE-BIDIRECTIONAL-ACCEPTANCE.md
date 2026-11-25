# Native POS and both-direction acceptance

Status: **BLOCKED**

No disposable native register was built or unlocked for this phase. The previous preview was the browser register, and that is not native acceptance. No executable path, hash, process id, or window handle was recorded.

Both applications read and write `/api/v1/expenses`, including category id, supplier id, and the bill payload. An expense id created by either client is the same row. That was proven by the API tests, not by opening the native POS and Business Pro on one expense.

Expense recording stays online. A failed request does not write a local expense or a petty-cash line.

## Commands

- `node scripts/python.mjs --env=development -m pytest tests/test_expenses.py -q` — 5 passed, exit 0.
- `pnpm exec vitest run src/features/expenses/expenseForm.test.ts src/features/expenses/compressBill.test.ts` from `apps/desktop` — 3 passed, exit 0.
- `pnpm exec tsc -p tsconfig.json --noEmit` from `apps/desktop` — exit 0.
