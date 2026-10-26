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
  job_title: string;
  nationality: string;
  phone: string;
  emirates_id: string;
  passport_number: string;
  joined_on: string | null;
  date_of_birth: string | null;
  basic_salary_cents: number;
  housing_allowance_cents: number;
  transport_allowance_cents: number;
  other_allowance_cents: number;
  overtime_rate_pct: number;
  is_active: boolean;
}

export interface Employee {
  user_id: string;
  name: string;
  role_name: string;
  store_id: string | null;
  profile: EmployeeProfile | null;
}

export interface PayrollLine {
  id: string;
  user_id: string;
  name: string;
  employee_code: string;
  basic_cents: number;
  allowances_cents: number;
  overtime_minutes: number;
  overtime_cents: number;
  commission_cents: number;
  bonus_cents: number;
  deductions_cents: number;
  unpaid_leave_days: number;
  leave_deduction_cents: number;
  note: string;
  net_cents: number;
}

export interface PayrollRun {
  id: string;
  year: number;
  month: number;
  status: "DRAFT" | "FINALIZED";
  currency: string;
  finalized_at: string | null;
  total_net_cents: number;
  lines: PayrollLine[];
}

export interface PayrollSettings {
  employer_id: string;
  bank_routing_code: string;
}
