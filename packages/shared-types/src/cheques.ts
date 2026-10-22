export type ChequeStatus = "RECEIVED" | "DEPOSITED" | "CLEARED" | "BOUNCED" | "CANCELLED";
export type ChequeAction = "deposit" | "clear" | "bounce" | "cancel";

export interface ChequeEvent {
  from_status: ChequeStatus | null;
  to_status: ChequeStatus;
  user_name: string | null;
  note: string;
  occurred_at: string;
}

export interface Cheque {
  id: string;
  store_id: string;
  customer_id: string | null;
  customer_name: string | null;
  cheque_number: string;
  bank: string;
  /** The date written on the cheque; post-dated cheques cannot be deposited before it. */
  cheque_date: string;
  amount_cents: number;
  currency: string;
  status: ChequeStatus;
  source: "SALE" | "LEDGER";
  sale_id: string | null;
  sale_reference: string | null;
  bounce_fee_cents: number;
  received_by_name: string | null;
  created_at: string;
  events: ChequeEvent[];
}

export interface ChequeStats {
  in_hand_count: number;
  in_hand_cents: number;
  deposited_count: number;
  deposited_cents: number;
  due_this_week_count: number;
  due_this_week_cents: number;
  bounced_count: number;
  bounced_cents: number;
  exposure_cents: number;
}

export interface ChequeList {
  stats: ChequeStats;
  cheques: Cheque[];
}

export const CHEQUE_STATUS_LABELS: Record<ChequeStatus, string> = {
  RECEIVED: "In hand",
  DEPOSITED: "Deposited",
  CLEARED: "Cleared",
  BOUNCED: "Bounced",
  CANCELLED: "Returned",
};
