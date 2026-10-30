import type { CustomerType, PaymentTerms, PriceTier } from "./enums.js";
import type { TaxTreatment } from "./tax.js";

export interface Customer {
  id: string;
  code: string;
  name: string;
  phone: string | null;
  email: string | null;
  customer_type: CustomerType;
  company_name: string | null;
  trn_vat_number: string | null;
  price_tier: PriceTier;
  credit_limit_cents: number;
  current_balance_cents: number;
  available_credit_cents: number;
  payment_terms: PaymentTerms;
  address: string | null;
  is_active: boolean;
  overdue_cents: number;
  open_invoice_count: number;
  /** Uncleared cheques already credited to the balance. */
  cheque_exposure_cents?: number;
  /** Blocks new on-account sales; set by a bounced cheque, long-overdue invoices, or a manager. */
  credit_hold?: boolean;
  credit_hold_reason?: string | null;
  whatsapp_opt_in?: boolean;
  sms_opt_in?: boolean;
  email_opt_in?: boolean;
  marketing_whatsapp_opt_in?: boolean;
  marketing_sms_opt_in?: boolean;
  marketing_email_opt_in?: boolean;
  loyalty_points?: number;
  /** Latest credit risk (0-100, higher is riskier) and grade A-E; null until first scored. */
  risk_score?: number | null;
  risk_grade?: RiskGrade | null;
  group_id?: string | null;
  /** Zero-rated / exempt customers pay no VAT on standard-rated lines while the certificate is valid. */
  tax_treatment?: TaxTreatment;
  tax_certificate_ref?: string | null;
  tax_certificate_expiry?: string | null;
  birthday?: string | null;
  gender?: "women" | "men" | "kids" | "unisex" | null;
  preferred_sizes?: Record<string, string>;
  notes?: string | null;
  tags?: string[];
  created_at: string;
  updated_at: string;
}

export type RiskGrade = "A" | "B" | "C" | "D" | "E";

export const RISK_GRADE_LABELS: Record<RiskGrade, string> = {
  A: "Low risk",
  B: "Moderate",
  C: "Watch",
  D: "High risk",
  E: "Severe",
};

export interface RiskFactor {
  key: string;
  label: string;
  points: number;
  detail: string;
}

export interface CreditRisk {
  customer_id: string;
  code: string;
  name: string;
  score: number;
  grade: RiskGrade;
  label: string;
  recommendation: string;
  suggested_limit_cents: number;
  credit_limit_cents: number;
  balance_cents: number;
  factors: RiskFactor[];
  computed_at: string | null;
}

export interface CustomerWrite {
  name: string;
  phone?: string | null;
  email?: string | null;
  customer_type: CustomerType;
  company_name?: string | null;
  trn_vat_number?: string | null;
  price_tier: PriceTier;
  credit_limit_cents: number;
  payment_terms: PaymentTerms;
  address?: string | null;
  is_active?: boolean;
  whatsapp_opt_in?: boolean;
  sms_opt_in?: boolean;
  email_opt_in?: boolean;
  marketing_whatsapp_opt_in?: boolean;
  marketing_sms_opt_in?: boolean;
  marketing_email_opt_in?: boolean;
  group_id?: string | null;
  tax_treatment?: TaxTreatment;
  tax_certificate_ref?: string | null;
  tax_certificate_expiry?: string | null;
  birthday?: string | null;
  gender?: "women" | "men" | "kids" | "unisex" | null;
  preferred_sizes?: Record<string, string>;
  notes?: string | null;
  tags?: string[];
}

export type CustomerUpdate = Partial<CustomerWrite>;

export type LedgerEntryType = "INVOICE" | "PAYMENT" | "ADJUSTMENT";

export interface LedgerEntry {
  id: string;
  entry_type: LedgerEntryType;
  amount_cents: number;
  balance_after_cents: number;
  sale_id: string | null;
  invoice: string | null;
  due_date: string | null;
  method: string | null;
  reference: string;
  note: string;
  created_at: string;
}

export interface OpenInvoice {
  sale_id: string;
  invoice: string;
  created_at: string;
  due_date: string | null;
  total_cents: number;
  amount_paid_cents: number;
  due_balance_cents: number;
  days_overdue: number;
  payment_status: string;
}

export interface Aging {
  current: number;
  days_1_30: number;
  days_31_60: number;
  days_61_90: number;
  days_90_plus: number;
}

export interface CustomerStatement {
  customer: Customer;
  currency: string;
  entries: LedgerEntry[];
  open_invoices: OpenInvoice[];
  aging: Aging;
  total_invoiced_cents: number;
  total_paid_cents: number;
  generated_at: string;
}

export type CollectionMethod = "cash" | "card" | "transfer";

export interface PaymentCreate {
  amount_cents: number;
  method: CollectionMethod | "cheque";
  reference?: string;
  note?: string;
  cheque?: { cheque_number: string; bank: string; cheque_date: string } | null;
}

export interface PaymentAllocation {
  sale_id: string;
  invoice: string;
  applied_cents: number;
  remaining_cents: number;
}

export interface PaymentResult {
  entry: LedgerEntry;
  allocations: PaymentAllocation[];
  unapplied_cents: number;
  customer: Customer;
}

export interface LedgerAdjustment {
  amount_cents: number;
  note: string;
}
