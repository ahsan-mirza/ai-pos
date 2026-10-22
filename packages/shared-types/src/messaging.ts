export type MessageChannel = "whatsapp" | "sms" | "email";
export type OutboundStatus = "QUEUED" | "SENT" | "FAILED" | "SKIPPED";

export interface MessagingSettings {
  /** Provider chosen per channel, e.g. { whatsapp: "log", sms: "http_sms", email: "smtp" }. */
  providers: Record<string, string>;
  available: Record<string, string[]>;
  /** Which events message customers automatically. */
  events: Record<string, boolean>;
}

export interface MessageTemplate {
  key: string;
  name: string;
  subject: string;
  body: string;
  is_active: boolean;
}

export interface OutboundMessage {
  id: string;
  channel: string;
  to_address: string;
  customer_name: string | null;
  template_key: string | null;
  subject: string;
  body: string;
  status: OutboundStatus;
  provider: string | null;
  attempts: number;
  last_error: string | null;
  created_at: string;
  sent_at: string | null;
}

export interface BackgroundJob {
  name: string;
  description: string;
  schedule: string;
  last_started_at: string | null;
  last_finished_at: string | null;
  last_status: string | null;
  last_result: string | null;
  run_count: number;
  running: boolean;
}

export const PROVIDER_LABELS: Record<string, string> = {
  log: "Log only (no delivery)",
  whatsapp_cloud: "WhatsApp Cloud API",
  http_sms: "SMS gateway (HTTP)",
  smtp: "Email (SMTP)",
};
