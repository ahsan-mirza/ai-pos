import type { TaxCategory } from "./tax.js";

export type BillStatus = "OPEN" | "PARTIAL" | "PAID" | "VOID";
export type SupplierPaymentMethod = "cash" | "transfer" | "card" | "cheque";
export type SupplierPaymentStatus = "POSTED" | "ISSUED" | "CLEARED" | "VOID";

export interface BillLine {
  id: string;
  product_id: string | null;
  description: string;
  quantity: number;
  unit_cost_cents: number;
  tax_category: TaxCategory;
  tax_cents: number;
  line_total_cents: number;
}

export interface SupplierBill {
  id: string;
  supplier_id: string;
  supplier_name: string;
  store_id: string;
  store_code: string;
  number: string;
  purchase_order_number: string | null;
  goods_receipt_number: string | null;
  bill_date: string;
  due_date: string;
  currency: string;
  subtotal_cents: number;
  tax_cents: number;
  total_cents: number;
  paid_cents: number;
  balance_cents: number;
  status: BillStatus;
  overdue_days: number;
  note: string;
  lines: BillLine[];
}

export interface SupplierPayment {
  id: string;
  supplier_id: string;
  supplier_name: string;
  amount_cents: number;
  currency: string;
  method: SupplierPaymentMethod;
  reference: string;
  paid_on: string;
  cheque_number: string | null;
  cheque_bank: string | null;
  cheque_date: string | null;
  status: SupplierPaymentStatus;
  note: string;
  allocations: { bill_id: string; bill_number: string; amount_cents: number }[];
  unallocated_cents: number;
}

export interface SupplierBalance {
  supplier_id: string;
  name: string;
  code: string;
  trn: string | null;
  payment_terms_days: number;
  open_bills: number;
  outstanding_cents: number;
  overdue_cents: number;
  due_7d_cents: number;
  credit_cents: number;
  cheques_issued_cents: number;
}

export interface PayablesSummary {
  outstanding_cents: number;
  overdue_cents: number;
  due_7d_cents: number;
  cheques_issued_cents: number;
  suppliers: SupplierBalance[];
}

export interface SupplierStatementRow {
  on: string;
  kind: "BILL" | "PAYMENT";
  reference: string;
  bill_cents: number;
  paid_cents: number;
  balance_cents: number;
  note: string;
}

export interface SupplierStatement {
  supplier: SupplierBalance;
  currency: string;
  rows: SupplierStatementRow[];
  aging: { current: number; days_1_30: number; days_31_60: number; days_61_90: number; days_90_plus: number };
  open_bills: SupplierBill[];
}

/** Stock received but not yet billed: a purchase-order receipt or an imported purchase batch. */
export interface UnbilledReceipt {
  goods_receipt_id: string | null;
  purchase_batch_id: string | null;
  number: string;
  purchase_order_number: string;
  supplier_id: string | null;
  supplier_name: string;
  store_code: string;
  received_on: string;
  units: number;
  value_cents: number;
}
