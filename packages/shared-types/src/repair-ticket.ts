import type { RepairStatus, SerialKind } from "./enums.js";

export interface RepairTicket {
  id: string;
  store_id: string;
  customer_name: string;
  customer_phone: string;
  device_model: string;
  identifier_kind: SerialKind;
  identifier_value: string;
  issue: string;
  status: RepairStatus;
  estimated_cost_cents: number;
  currency: string;
  created_at: string;
  updated_at: string;
}

export type RepairLineKind = "PART" | "LABOUR";

export interface RepairEvent {
  from_status: RepairStatus | null;
  to_status: RepairStatus;
  note: string;
  /** register, portal, or migration */
  source: string;
  user_name: string | null;
  occurred_at: string;
}

export interface RepairLine {
  id: string;
  kind: RepairLineKind;
  product_id: string;
  sku: string;
  description: string;
  quantity: number;
  unit_price_cents: number;
  line_cents: number;
  reserved_quantity?: number;
}

export interface RepairAttachment {
  id: string;
  kind: "INTAKE" | "DIAGNOSIS" | "AFTER";
  file_name: string;
  content_type: string;
  size_bytes: number;
  created_at: string;
}

export interface RepairDeposit {
  id: string;
  amount_cents: number;
  method: string;
  reference: string;
  status: "HELD" | "APPLIED" | "REFUNDED";
  received_at: string;
  received_by_name: string | null;
}

export interface RepairDetail extends RepairTicket {
  customer_id: string | null;
  warranty_status: "IN_WARRANTY" | "EXPIRED" | "NOT_FOUND" | null;
  sale_id: string | null;
  invoice_number: string | null;
  events: RepairEvent[];
  lines: RepairLine[];
  parts_cents: number;
  labour_cents: number;
  total_cents: number;
  reference?: string;
  technician_name?: string | null;
  priority?: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  promised_at?: string | null;
  has_passcode?: boolean;
  accessories?: string;
  approval_status?: "PENDING" | "APPROVED" | "DECLINED" | null;
  approval_amount_cents?: number | null;
  approval_note?: string;
  tracking_url?: string | null;
  deposit_held_cents?: number;
  balance_due_cents?: number;
  parts_short?: boolean;
  attachments?: RepairAttachment[];
  deposits?: RepairDeposit[];
  repair_warranty?: { id: string; starts_at: string; expires_at: string; status: string } | null;
}

export interface RepairBoardCard {
  id: string;
  reference: string;
  device_model: string;
  customer_name: string;
  issue: string;
  status: RepairStatus;
  priority: "LOW" | "NORMAL" | "HIGH" | "URGENT";
  technician_name: string | null;
  promised_at: string | null;
  overdue: boolean;
  approval_status: "PENDING" | "APPROVED" | "DECLINED" | null;
  parts_short: boolean;
  deposit_held_cents: number;
  estimated_cost_cents: number;
  currency: string;
}

export interface RepairBoard {
  columns: { status: RepairStatus; cards: RepairBoardCard[] }[];
  technicians: { id: string; name: string }[];
}

export interface RepairTicketUpsert {
  id: string;
  store_id: string;
  customer_name: string;
  customer_phone: string;
  device_model: string;
  identifier_kind: SerialKind;
  identifier_value: string;
  issue: string;
  status: RepairStatus;
  estimated_cost_cents: number;
  currency: string;
}
