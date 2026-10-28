import type { BusinessProfile, Capability } from "./capabilities.js";

export type OverrideState = "on" | "off";

/** GET /api/v1/tenant/modules: the locked business type and the modules that fit it. */
export interface TenantModules {
  tenant_name: string;
  business_profile: BusinessProfile;
  profile_label: string;
  /** True once onboarding is done: the business type then only changes through IT support. */
  locked: boolean;
  enabled: Capability[];
  /** The business-type preset. Included with the store. */
  base: Capability[];
  /** Compatible with the business type, and not part of the preset. */
  optional: Capability[];
  /** Fit this business type and can be switched on by the tenant. */
  available: Capability[];
  planned: Capability[];
  /** Set by IT support; the tenant cannot change these. */
  managed: Partial<Record<Capability, OverrideState>>;
  support_email: string;
}

export type ChangeKind = "BUSINESS_TYPE" | "MODULE";
export type ChangeStatus = "PENDING" | "RESOLVED" | "REJECTED";

export interface ChangeRequestInput {
  kind: ChangeKind;
  requested_value: string;
  reason: string;
}

export interface ChangeRequest {
  id: string;
  tenant_id: string;
  kind: ChangeKind;
  requested_value: string;
  current_value: string | null;
  reason: string;
  snapshot: Record<string, number>;
  status: ChangeStatus;
  requested_by_email: string | null;
  requested_by_name: string | null;
  resolution_notes: string | null;
  created_at: string;
  resolved_at: string | null;
}

/** Subject line support uses to file a business-type change. */
export function supportMailto(supportEmail: string, tenantName: string): string {
  const subject = `Business Type Change Request - ${tenantName}`;
  return `mailto:${supportEmail}?subject=${encodeURIComponent(subject)}`;
}
