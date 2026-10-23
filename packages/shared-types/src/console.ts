import type { ChangeRequest, OverrideState } from "./governance.js";

/** Types of the POS-company console API (/api/v1/super-admin). */
export type OperatorRole = "SUPPORT" | "ADMIN";
export type TenantStatus = "active" | "suspended";

export interface Operator {
  id: string;
  email: string;
  full_name: string;
  role: OperatorRole;
  is_active: boolean;
  last_login_at: string | null;
}

export interface ConsoleSession {
  access_token: string;
  token_type: string;
  expires_in: number;
  operator: Operator;
}

export interface TenantStats {
  onboarded: boolean | null;
  business_profile: string | null;
  enabled_modules: string[];
  stores: number;
  registers: number;
  users: number;
  customers: number;
  products: number;
  sales_30d_count: number;
  sales_30d_cents: number;
  currency: string | null;
  last_sale_at: string | null;
  db_size_bytes: number | null;
  collected_at: string | null;
}

export interface TenantRow {
  id: string;
  slug: string;
  name: string;
  domain: string;
  status: TenantStatus;
  business_profile: string;
  profile_label: string;
  plan: string;
  plan_name: string;
  practice_mode: boolean;
  owner_email: string | null;
  created_at: string;
  stats: TenantStats;
  pending_requests: number;
}

export interface ModuleState {
  key: string;
  label: string;
  available: boolean;
  enabled: boolean;
  selected: boolean;
  fits_type: boolean;
  override: OverrideState | null;
}

export interface OperatorAudit {
  id: string;
  operator_email: string | null;
  action: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  reason: string | null;
  created_at: string;
}

export interface TenantDetail {
  tenant: TenantRow;
  modules: ModuleState[];
  change_requests: ChangeRequest[];
  audit: OperatorAudit[];
  unreachable: string | null;
}

export interface MigrationCheck {
  code: string;
  message: string;
  count: number;
}

export interface MigrationPreflight {
  tenant_id: string;
  current_profile: string;
  target_profile: string;
  gained: string[];
  lost: string[];
  blockers: MigrationCheck[];
  warnings: MigrationCheck[];
  preflight_token: string;
  expires_at: string;
}

export interface ConsoleChangeRequest extends ChangeRequest {
  tenant_slug: string;
  tenant_name: string;
}

export interface ConsoleCustomer {
  id: string;
  name: string;
  phone: string | null;
  email: string | null;
  customer_type: string;
  balance_cents: number;
  created_at: string | null;
}
