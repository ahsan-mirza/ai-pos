/** Provider payments: QR codes, integrated card terminals and buy-now-pay-later (Tabby, Tamara). */

export type PaymentChannel = "QR" | "CARD" | "BNPL";
export type PaymentIntentStatus = "PENDING" | "AUTHORIZED" | "PAID" | "DECLINED" | "EXPIRED" | "CANCELLED";
export type PaymentRefundStatus = "PENDING" | "SUCCEEDED" | "FAILED";

export interface PaymentIntent {
  id: string;
  channel: PaymentChannel;
  provider: string;
  amount_cents: number;
  currency: string;
  reference: string;
  qr_payload: string;
  status: PaymentIntentStatus;
  expires_at: string;
  paid_at: string | null;
  sale_id: string | null;
  /** BNPL: the provider's checkout page the customer opens. */
  customer_url: string | null;
  auth_code: string | null;
  card_brand: string | null;
  card_last4: string | null;
  failure_reason: string | null;
  refunded_cents: number;
  terminal_id: string | null;
  /** Handled by the simulator: staff approve or decline it by hand. */
  simulated: boolean;
}

export interface PaymentRow extends PaymentIntent {
  store_id: string;
  store_name: string;
  created_at: string;
  sale_number: string | null;
}

export interface PaymentList {
  items: PaymentRow[];
  total: number;
  paid_cents: number;
  refunded_cents: number;
}

export interface PaymentRefund {
  id: string;
  intent_id: string;
  return_id: string | null;
  provider: string;
  channel: PaymentChannel;
  amount_cents: number;
  status: PaymentRefundStatus;
  provider_ref: string | null;
  error: string | null;
  attempts: number;
  created_at: string;
}

export type CardTerminalProvider = "simulator" | "ngenius" | "geidea";
export type BnplProvider = "simulator" | "tabby" | "tamara";

export interface PaymentTerminal {
  id: string;
  store_id: string;
  provider: CardTerminalProvider;
  terminal_ref: string;
  label: string;
  device_id: string | null;
  is_active: boolean;
  last_checked_at: string | null;
  last_check_ok: boolean | null;
}

export interface PaymentTerminalInput {
  store_id: string;
  provider: CardTerminalProvider;
  terminal_ref: string;
  label: string;
  device_id?: string | null;
  is_active?: boolean;
}

export interface PaymentProvider {
  name: string;
  label: string;
  channel: "CARD" | "BNPL";
  /** Credentials are set; otherwise the simulator stands in. */
  configured: boolean;
  simulated: boolean;
  /** Environment keys still missing, e.g. TABBY_SECRET_KEY. */
  missing: string[];
}

export interface PaymentsConfig {
  card_provider: PaymentProvider;
  bnpl: PaymentProvider[];
  terminals: PaymentTerminal[];
  /** The store has an active terminal: card tenders go through it, or a manager approves a manual entry. */
  card_terminal_required: boolean;
  default_terminal_id: string | null;
  simulator_controls: boolean;
}

export const PAYMENT_PROVIDER_LABELS: Record<string, string> = {
  simulator: "Simulator",
  ngenius: "N-Genius",
  geidea: "Geidea",
  tabby: "Tabby",
  tamara: "Tamara",
  dev: "Dev QR",
  emvco: "EMVCo QR",
};

export const PAYMENT_STATUS_LABELS: Record<PaymentIntentStatus, string> = {
  PENDING: "Waiting",
  AUTHORIZED: "Approved, capturing",
  PAID: "Paid",
  DECLINED: "Declined",
  EXPIRED: "Expired",
  CANCELLED: "Cancelled",
};
