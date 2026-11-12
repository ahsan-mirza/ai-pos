export interface TimeEntry {
  id: string;
  user_id: string;
  store_code: string;
  clock_in_at: string;
  clock_out_at: string | null;
  break_minutes: number;
  worked_minutes: number;
  overtime_minutes: number;
  status: "OPEN" | "CLOSED" | "APPROVED";
  source: string;
  edit_note: string;
  edited_by_name: string | null;
  approved_by_name: string | null;
  forgotten: boolean;
}

export interface StaffTimesheet {
  user_id: string;
  name: string;
  role_name: string;
  worked_minutes: number;
  overtime_minutes: number;
  days_worked: number;
  open_entries: number;
  pending_approval: number;
  entries: TimeEntry[];
}

export interface TimesheetReport {
  period_from: string;
  period_to: string;
  daily_hours: number;
  staff: StaffTimesheet[];
}

export type CommissionBasis = "NET_SALES" | "GROSS_PROFIT";

export interface CommissionRule {
  id: string;
  name: string;
  basis: CommissionBasis;
  rate_bps: number;
  category_ids: string[];
  role_ids: string[];
  threshold_cents: number;
  is_active: boolean;
}

export interface StaffCommission {
  user_id: string;
  name: string;
  role_name: string;
  lines: number;
  commission_cents: number;
  by_rule: { rule_id: string; rule_name: string; basis_cents: number; commission_cents: number }[];
}

export interface CommissionReport {
  period_from: string;
  period_to: string;
  currency: string;
  total_cents: number;
  staff: StaffCommission[];
}

export interface EmployeeProfile {
  /** Assigned by the server the first time the profile is saved. */
  employee_code: string;
  labour_id: string;
  bank_routing_code: string;
  iban: string;
  iban_masked?: boolean;
  bank_name: string;
  account_holder: string;
  job_title: string;
  nationality: string;
  phone: string;
  emirates_id: string;
  passport_number: string;
  joined_on: string | null;
  date_of_birth: string | null;
  employment_type: string;
  basic_salary_cents: number;
  housing_allowance_cents: number;
  transport_allowance_cents: number;
  food_allowance_cents: number;
  other_allowance_cents: number;
  variable_allowance_cents: number;
  recurring_deduction_cents: number;
  components: SalaryComponent[];
  overtime_rate_pct: number;
  overtime_eligible: boolean;
  commission_eligible: boolean;
  salary_frequency: "MONTHLY";
  profile_status: "DRAFT" | "ACTIVE";
  effective_from: string | null;
  is_active: boolean;
}

export interface SalaryComponent {
  name: string;
  kind: "ALLOWANCE" | "DEDUCTION";
  code: string;
  amount_cents: number;
  taxable: boolean;
  active: boolean;
}

export interface SalaryVersion {
  id: string;
  effective_from: string;
  effective_to: string | null;
  status: string;
  basic_salary_cents: number;
  housing_allowance_cents: number;
  transport_allowance_cents: number;
  food_allowance_cents: number;
  other_allowance_cents: number;
  variable_allowance_cents: number;
  recurring_deduction_cents: number;
  overtime_rate_pct: number;
  overtime_eligible: boolean;
  commission_eligible: boolean;
}

export interface Employee {
  user_id: string;
  name: string;
  role_name: string;
  store_id: string | null;
  store_name: string;
  employment_status: "ACTIVE" | "INACTIVE";
  profile: EmployeeProfile | null;
  salary_history: SalaryVersion[];
}

export interface PayComponent {
  name: string;
  kind: "EARNING" | "DEDUCTION";
  cents: number;
  source: string;
}

export interface PayrollException {
  user_id: string | null;
  name: string;
  severity: "EXCLUDED" | "WARNING";
  code: string;
  message: string;
}

export interface PayrollLine {
  id: string;
  user_id: string;
  name: string;
  employee_code: string;
  store_id: string | null;
  store_name: string;
  basic_cents: number;
  allowances_cents: number;
  overtime_minutes: number;
  overtime_cents: number;
  commission_cents: number;
  bonus_cents: number;
  deductions_cents: number;
  recurring_deduction_cents: number;
  unpaid_leave_days: number;
  leave_deduction_cents: number;
  gross_cents: number;
  note: string;
  net_cents: number;
  calculation_status: string;
  components: PayComponent[];
  formula: string;
}

export type PayrollRunStatus = "DRAFT" | "UNDER_REVIEW" | "FINALIZED" | "CANCELLED";
export type PayrollPaymentStatus =
  | "NONE"
  | "GENERATED"
  | "SUBMITTED"
  | "PROCESSING"
  | "PARTIALLY_PAID"
  | "PAID"
  | "REJECTED"
  | "FAILED";

export interface PayrollRun {
  id: string;
  year: number;
  month: number;
  status: PayrollRunStatus;
  payment_status: PayrollPaymentStatus;
  store_id: string | null;
  currency: string;
  finalized_at: string | null;
  total_gross_cents: number;
  total_deductions_cents: number;
  total_net_cents: number;
  exceptions: PayrollException[];
  lines: PayrollLine[];
}

export interface PayrollSettings {
  employer_id: string;
  bank_routing_code: string;
  bank_name: string;
  employer_reference: string;
  segregate_approval: boolean;
}

export interface WpsValidation {
  ready: boolean;
  provider: string;
  provider_note: string;
  issues: { user_id: string | null; employee_code: string; name: string; code: string; message: string }[];
}

export interface PayrollPayment {
  id: string;
  amount_cents: number;
  reference: string;
  status: string;
  note: string;
  created_at: string;
}
