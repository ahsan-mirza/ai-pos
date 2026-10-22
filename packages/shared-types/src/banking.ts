export type BankLineStatus = "UNMATCHED" | "MATCHED" | "IGNORED";
export type BookKind =
  | "CARD_SETTLEMENT"
  | "QR_SETTLEMENT"
  | "BNPL_SETTLEMENT"
  | "TRANSFER_RECEIPT"
  | "ACCOUNT_RECEIPT"
  | "CHEQUE_DEPOSIT"
  | "SUPPLIER_PAYMENT"
  | "EXPENSE"
  | "PETTY_CASH_TOPUP"
  | "PAYROLL";

export const BOOK_KIND_LABELS: Record<BookKind, string> = {
  CARD_SETTLEMENT: "Card settlement",
  QR_SETTLEMENT: "QR settlement",
  BNPL_SETTLEMENT: "Pay-later payout",
  TRANSFER_RECEIPT: "Transfer at the till",
  ACCOUNT_RECEIPT: "Account payment",
  CHEQUE_DEPOSIT: "Cheque deposit",
  SUPPLIER_PAYMENT: "Supplier payment",
  EXPENSE: "Expense",
  PETTY_CASH_TOPUP: "Petty cash top-up",
  PAYROLL: "Payroll",
};

export interface BankAccount {
  id: string;
  name: string;
  bank: string;
  iban: string | null;
  currency: string;
  is_active: boolean;
  unmatched_count: number;
  statement_balance_cents: number | null;
  last_statement_on: string | null;
}

export interface BankAccountWrite {
  name: string;
  bank: string;
  iban: string | null;
  is_active: boolean;
}

export interface BankStatement {
  id: string;
  file_name: string;
  file_format: "CSV" | "MT940";
  period_from: string | null;
  period_to: string | null;
  lines_imported: number;
  lines_skipped: number;
  imported_at: string;
  imported_by_name: string | null;
}

export interface StatementImport {
  statement: BankStatement;
  auto_matched: number;
}

export interface BankStatementLine {
  id: string;
  booked_on: string;
  description: string;
  reference: string;
  amount_cents: number;
  balance_cents: number | null;
  status: BankLineStatus;
  matched_key: string | null;
  matched_label: string;
  fee_cents: number;
  auto_matched: boolean;
  match_note: string;
}

export interface BookItem {
  key: string;
  kind: BookKind;
  booked_on: string;
  amount_cents: number;
  label: string;
  reference: string;
  store_code: string | null;
}

export interface MatchCandidate extends BookItem {
  score: number;
  fee_cents: number;
}

export interface ReconciliationSummary {
  account_id: string;
  lines: number;
  matched: number;
  unmatched: number;
  ignored: number;
  unmatched_in_cents: number;
  unmatched_out_cents: number;
  fees_cents: number;
  statement_balance_cents: number | null;
  period_from: string | null;
  period_to: string | null;
  outstanding: BookItem[];
}
