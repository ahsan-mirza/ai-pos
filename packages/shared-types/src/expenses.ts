export type ExpenseCategory =
  | "RENT"
  | "UTILITIES"
  | "SALARIES"
  | "TRANSPORT"
  | "MARKETING"
  | "MAINTENANCE"
  | "OFFICE"
  | "BANK_FEES"
  | "OTHER";

export const EXPENSE_CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  RENT: "Rent",
  UTILITIES: "Utilities & telecom",
  SALARIES: "Salaries & wages",
  TRANSPORT: "Transport & fuel",
  MARKETING: "Marketing",
  MAINTENANCE: "Repairs & maintenance",
  OFFICE: "Office & supplies",
  BANK_FEES: "Bank & card fees",
  OTHER: "Other",
};

export type ExpensePaidFrom = "PETTY_CASH" | "BANK" | "CARD";

export interface Expense {
  id: string;
  number: string;
  store_id: string;
  store_code: string;
  category: string;
  category_id: string | null;
  category_name: string;
  description: string;
  payee: string;
  payee_trn: string | null;
  supplier_id: string | null;
  supplier_name: string;
  supplier_code: string;
  spent_on: string;
  net_cents: number;
  tax_cents: number;
  recoverable_tax_cents: number;
  total_cents: number;
  currency: string;
  has_tax_invoice: boolean;
  has_bill: boolean;
  paid_from: ExpensePaidFrom;
  reference: string;
  status: "RECORDED" | "VOID";
  created_by_name: string | null;
  void_reason: string;
}

export interface ExpenseSupplier {
  id: string;
  name: string;
  code: string;
  phone: string | null;
  trn: string | null;
  is_active: boolean;
}

export interface ExpenseCategoryOption {
  id: string;
  code: string;
  name: string;
  description: string;
  is_active: boolean;
  sort_order: number;
}

export interface ExpenseBill {
  file_name: string;
  content_type: string;
  original_size_bytes: number;
  size_bytes: number;
  data_base64: string;
}

export interface ExpenseList {
  items: Expense[];
  total_cents: number;
  recoverable_tax_cents: number;
  by_category: { category: string; category_name: string; total_cents: number; count: number }[];
}

export interface PettyCashEntry {
  id: string;
  kind: "TOPUP" | "EXPENSE" | "VOID" | "COUNT";
  amount_cents: number;
  balance_after: number;
  expense_number: string | null;
  note: string;
  user_name: string | null;
  created_at: string;
}

export interface PettyCash {
  store_id: string;
  store_code: string;
  balance_cents: number;
  entries: PettyCashEntry[];
}
