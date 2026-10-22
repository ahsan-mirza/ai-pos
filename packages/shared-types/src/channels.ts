export interface DeliveryChannelInput {
  name: string;
  /** Lowercase letters, digits and dashes; part of the webhook URL. */
  code: string;
  store_id: string;
  commission_bps: number;
  price_markup_bps: number;
  auto_accept: boolean;
  default_prep_minutes: number;
  is_active: boolean;
}

export interface DeliveryChannel extends DeliveryChannelInput {
  id: string;
  adapter: string;
  webhook_path: string;
  created_at: string;
}

/** Returned once, on create or rotate: the secret that signs the channel's webhooks. */
export interface DeliveryChannelSecret {
  channel: DeliveryChannel;
  webhook_secret: string;
}

export type ChannelStatus = "PENDING" | "ACCEPTED" | "REJECTED" | "COMPLETED";

export interface ChannelPayout {
  id: string;
  channel_id: string;
  channel_name: string;
  amount_cents: number;
  commission_cents: number;
  reference: string | null;
  note: string | null;
  received_at: string;
}

export interface ChannelSettlementRow {
  channel_id: string;
  name: string;
  commission_bps: number;
  orders: number;
  gross_cents: number;
  commission_cents: number;
  net_cents: number;
  paid_out_cents: number;
  outstanding_cents: number;
}

export interface ChannelSettlementReport {
  start: string;
  end: string;
  rows: ChannelSettlementRow[];
  payouts: ChannelPayout[];
}
