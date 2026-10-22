export type GlAccountType = "ASSET" | "LIABILITY" | "EQUITY" | "INCOME" | "EXPENSE";

export const GL_ACCOUNT_TYPE_LABELS: Record<GlAccountType, string> = {
  ASSET: "Asset",
  LIABILITY: "Liability",
  EQUITY: "Equity",
  INCOME: "Income",
  EXPENSE: "Expense",
};

export const JOURNAL_LABELS: Record<string, string> = {
  SALES: "Sales",
  COGS: "Cost of sales",
  RETURNS: "Returns",
  RECEIPTS: "Customer receipts",
  STOCK: "Stock",
  PURCHASES: "Supplier bills",
  PAYMENTS: "Supplier payments",
  EXPENSES: "Expenses",
  TRADEINS: "Trade-ins",
  PAYROLL: "Payroll",
  BANK: "Bank",
  CHEQUES: "Cheques",
  MANUAL: "Manual",
  CLOSING: "Year-end close",
  REVERSAL: "Reversal",
};

export interface GlAccountRow {
  id: string;
  code: string;
  name: string;
  type: GlAccountType;
  is_system: boolean;
  is_active: boolean;
  balance_cents: number;
}

export interface AccountingSettings {
  fiscal_year_start_month: number;
  locked_until: string | null;
}

export interface PostResult {
  posted: number;
  reversed: number;
  unchanged: number;
  unbalanced: string[];
}

export interface JournalEntryLine {
  account_id: string;
  account_code: string;
  account_name: string;
  debit_cents: number;
  credit_cents: number;
  memo: string;
}

export interface JournalEntry {
  id: string;
  number: number;
  entry_date: string;
  original_date: string | null;
  journal: string;
  reference: string;
  memo: string;
  source_ref: string | null;
  is_active: boolean;
  reversal_of_id: string | null;
  reversible: boolean;
  total_cents: number;
  created_by_name: string | null;
  created_at: string;
  lines: JournalEntryLine[];
}

export interface TrialBalanceRow {
  account_id: string;
  code: string;
  name: string;
  type: GlAccountType;
  opening_cents: number;
  debit_cents: number;
  credit_cents: number;
  closing_cents: number;
}

export interface TrialBalance {
  period_from: string;
  period_to: string;
  currency: string;
  rows: TrialBalanceRow[];
  total_debit_cents: number;
  total_credit_cents: number;
}

export interface FinancialStatementRow {
  account_id: string | null;
  code: string;
  name: string;
  amount_cents: number;
}

export interface FinancialStatementSection {
  key: string;
  title: string;
  rows: FinancialStatementRow[];
  total_cents: number;
}

export interface SubledgerCheck {
  key: "inventory" | "receivables" | "payables";
  label: string;
  books_cents: number;
  subledger_cents: number;
  difference_cents: number;
}

export interface BalanceSheet {
  as_of: string;
  currency: string;
  sections: FinancialStatementSection[];
  total_assets_cents: number;
  total_liabilities_cents: number;
  total_equity_cents: number;
  balanced: boolean;
  checks: SubledgerCheck[];
}

export interface IncomeStatement {
  period_from: string;
  period_to: string;
  currency: string;
  sections: FinancialStatementSection[];
  gross_profit_cents: number;
  operating_profit_cents: number;
  net_profit_cents: number;
}

export interface AccountLedgerRow {
  entry_id: string;
  number: number;
  entry_date: string;
  journal: string;
  reference: string;
  memo: string;
  debit_cents: number;
  credit_cents: number;
  balance_cents: number;
}

export interface AccountLedger {
  account: GlAccountRow;
  period_from: string;
  period_to: string;
  opening_cents: number;
  closing_cents: number;
  rows: AccountLedgerRow[];
  truncated: boolean;
}

export interface CorporateTaxEstimate {
  fiscal_year: number;
  period_from: string;
  period_to: string;
  currency: string;
  revenue_cents: number;
  profit_before_tax_cents: number;
  add_backs_cents: number;
  deductions_cents: number;
  taxable_income_cents: number;
  threshold_cents: number;
  rate_bps: number;
  tax_cents: number;
  small_business_relief_eligible: boolean;
  provision_posted_cents: number;
  notes: string[];
}
