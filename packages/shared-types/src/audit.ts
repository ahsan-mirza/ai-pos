export const AuditActionType = {
  Create: "CREATE",
  Update: "UPDATE",
  Delete: "DELETE",
  ManualStockAdjustment: "MANUAL_STOCK_ADJUSTMENT",
  PriceOverride: "PRICE_OVERRIDE",
  CreditLimitOverride: "CREDIT_LIMIT_OVERRIDE",
  RoleChange: "ROLE_CHANGE",
  RefundProcessed: "REFUND_PROCESSED",
  ManagerOverride: "MANAGER_OVERRIDE",
  LoginPin: "LOGIN_PIN",
  LoginPassword: "LOGIN_PASSWORD",
  ExportData: "EXPORT_DATA",
  DrawerOpen: "DRAWER_OPEN",
  CashDrop: "CASH_DROP",
  ItemVoid: "ITEM_VOID",
  ExpiredStockSold: "EXPIRED_STOCK_SOLD",
} as const;
export type AuditActionType = (typeof AuditActionType)[keyof typeof AuditActionType];

export const SENSITIVE_AUDIT_ACTIONS: readonly AuditActionType[] = [
  "MANUAL_STOCK_ADJUSTMENT",
  "PRICE_OVERRIDE",
  "CREDIT_LIMIT_OVERRIDE",
  "ROLE_CHANGE",
  "REFUND_PROCESSED",
  "MANAGER_OVERRIDE",
  "DRAWER_OPEN",
  "ITEM_VOID",
];

export const AUDIT_ACTION_LABELS: Record<AuditActionType, string> = {
  CREATE: "Created",
  UPDATE: "Updated",
  DELETE: "Deleted",
  MANUAL_STOCK_ADJUSTMENT: "Stock adjustment",
  PRICE_OVERRIDE: "Price override",
  CREDIT_LIMIT_OVERRIDE: "Credit override",
  ROLE_CHANGE: "Role change",
  REFUND_PROCESSED: "Refund",
  MANAGER_OVERRIDE: "Manager override",
  LOGIN_PIN: "PIN login",
  LOGIN_PASSWORD: "Password login",
  EXPORT_DATA: "Data export",
  DRAWER_OPEN: "Drawer opened",
  CASH_DROP: "Cash drop",
  ITEM_VOID: "Item void",
  EXPIRED_STOCK_SOLD: "Expired stock sold",
};

export type AuditClientDevice = "web" | "desktop" | "api" | "system";

export interface AuditLogRow {
  id: string;
  occurred_at: string;
  created_at: string;
  user_id: string | null;
  user_name: string | null;
  user_role: string | null;
  approver_id: string | null;
  approver_name: string | null;
  store_id: string | null;
  store_code: string | null;
  store_name: string | null;
  action_type: AuditActionType;
  action: string;
  target_entity: string;
  target_entity_id: string | null;
  reason_notes: string | null;
  client_device: AuditClientDevice;
  ip_address: string | null;
  changed_fields: string[];
  sensitive: boolean;
}

export interface AuditLogDetail extends AuditLogRow {
  old_values: Record<string, unknown> | null;
  new_values: Record<string, unknown> | null;
  details: Record<string, unknown>;
  request_path: string | null;
  client_event_id: string | null;
}

export interface AuditLogPage {
  total: number;
  limit: number;
  offset: number;
  rows: AuditLogRow[];
}

export interface AuditActiveStaff {
  user_id: string;
  user_name: string;
  user_role: string | null;
  store_code: string | null;
  client_device: AuditClientDevice;
  last_login_at: string;
}

export interface AuditSummary {
  since: string;
  total_actions: number;
  sensitive_overrides: number;
  active_staff_sessions: number;
  session_window_minutes: number;
  active_staff: AuditActiveStaff[];
  by_action_type: Partial<Record<AuditActionType, number>>;
}

export interface AuditFacets {
  users: { id: string; name: string; role: string | null }[];
  entities: string[];
  action_types: AuditActionType[];
}

export interface AuditLogQuery {
  from?: string;
  to?: string;
  user_id?: string;
  store_id?: string;
  action_type?: AuditActionType[];
  target_entity?: string;
  q?: string;
  sensitive_only?: boolean;
}

/** Register-side actions that are queued offline and batch-synced to the ledger. */
export type DesktopAuditActionType = Extract<
  AuditActionType,
  "LOGIN_PIN" | "MANAGER_OVERRIDE" | "PRICE_OVERRIDE" | "DRAWER_OPEN" | "CASH_DROP" | "ITEM_VOID" | "REFUND_PROCESSED"
>;

export interface DesktopAuditEvent {
  id: string;
  occurred_at: string;
  action_type: DesktopAuditActionType;
  action: string;
  user_id: string;
  approver_id?: string | null;
  store_id: string;
  target_entity: string;
  target_entity_id?: string | null;
  reason_notes?: string | null;
  old_values?: Record<string, unknown> | null;
  new_values?: Record<string, unknown> | null;
  details?: Record<string, unknown>;
}

export interface DesktopAuditResult {
  accepted: string[];
  duplicates: string[];
  rejected: { id: string; reason: string }[];
}

export type FieldChange = "added" | "removed" | "modified" | "unchanged";

/** Field-by-field comparison of an entry's before/after snapshots, changed fields first. */
export function diffAuditValues(
  before: Record<string, unknown> | null,
  after: Record<string, unknown> | null,
): { field: string; change: FieldChange; before: unknown; after: unknown }[] {
  const old = before ?? {};
  const next = after ?? {};
  const fields = [...new Set([...Object.keys(old), ...Object.keys(next)])];
  const rank: Record<FieldChange, number> = { modified: 0, added: 1, removed: 2, unchanged: 3 };
  return fields
    .map((field) => {
      const inOld = field in old;
      const inNew = field in next;
      const change: FieldChange =
        inOld && !inNew
          ? "removed"
          : !inOld && inNew
            ? "added"
            : JSON.stringify(old[field]) === JSON.stringify(next[field])
              ? "unchanged"
              : "modified";
      return { field, change, before: old[field], after: next[field] };
    })
    .sort((a, b) => rank[a.change] - rank[b.change] || a.field.localeCompare(b.field));
}
