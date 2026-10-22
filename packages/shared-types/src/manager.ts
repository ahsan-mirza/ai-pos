export type ApprovalKind = "PRICE_OVERRIDE" | "BELOW_FLOOR" | "CREDIT_LIMIT" | "REFUND";
export type ApprovalStatus = "PENDING" | "APPROVED" | "DECLINED" | "CANCELLED" | "EXPIRED";

export const APPROVAL_KIND_LABELS: Record<ApprovalKind, string> = {
  PRICE_OVERRIDE: "Price override",
  BELOW_FLOOR: "Below margin floor",
  CREDIT_LIMIT: "Credit limit",
  REFUND: "Refund",
};

export interface ApprovalRequest {
  id: string;
  kind: ApprovalKind;
  status: ApprovalStatus;
  store_id: string | null;
  store_code: string | null;
  requested_by_name: string | null;
  title: string;
  details: string[];
  amount_cents: number | null;
  created_at: string;
  expires_at: string;
  decided_at: string | null;
  decided_by_name: string | null;
  note: string;
}

export interface BranchToday {
  store_id: string;
  store_code: string;
  store_name: string;
  sales: number;
  revenue_cents: number;
  refunds_cents: number;
  net_cents: number;
  average_basket_cents: number;
  last_sale_at: string | null;
}

export interface ManagerDashboard {
  currency: string;
  as_of: string;
  net_cents: number;
  sales: number;
  yesterday_net_cents: number;
  hourly_cents: number[];
  branches: BranchToday[];
  top_products: { product_id: string; name: string; quantity: number; revenue_cents: number }[];
  attention: {
    approvals: number;
    timesheets: number | null;
    credit_holds: number | null;
    cheques_to_deposit: number | null;
  };
}

export interface PendingTimeEntry {
  id: string;
  user_name: string;
  store_code: string;
  clock_in_at: string;
  clock_out_at: string;
  break_minutes: number;
  worked_minutes: number;
}

export interface CreditHoldRow {
  customer_id: string;
  name: string;
  balance_cents: number;
  credit_limit_cents: number;
  reason: string | null;
  manual: boolean;
}
