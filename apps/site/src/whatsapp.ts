import { isValidE164 } from "@ai-pos/ui";

export interface PublicWhatsApp {
  enabled: boolean;
  /** Digits with the country code, without a leading plus. */
  number: string;
  message: string;
  tooltip: string;
  /** Public sales address, or blank when the console has not published one. */
  email: string;
}

export const EMPTY_WHATSAPP: PublicWhatsApp = {
  enabled: false,
  number: "",
  message: "",
  tooltip: "Chat with Sales",
  email: "",
};

const MESSAGE_LIMIT = 500;
const TOOLTIP_LIMIT = 40;
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export function whatsappDigits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Digits for wa.me when an admin published a complete international number. */
export function publishedWhatsapp(contact: PublicWhatsApp): string | null {
  if (!contact.enabled) return null;
  const digits = whatsappDigits(contact.number);
  if (!isValidE164(`+${digits}`)) return null;
  return digits;
}

/** The floating button is shown only when an admin published a usable number. */
export function whatsappReady(contact: PublicWhatsApp): boolean {
  return publishedWhatsapp(contact) !== null;
}

/** Standard click-to-chat link. The visitor still has to send the prefilled message. */
export function whatsappChatUrl(number: string, message: string): string {
  const digits = whatsappDigits(number);
  const text = message.trim();
  const base = `https://wa.me/${digits}`;
  return text.length > 0 ? `${base}?text=${encodeURIComponent(text)}` : base;
}

export function parsePublicWhatsApp(body: unknown): PublicWhatsApp {
  if (body === null || typeof body !== "object") return EMPTY_WHATSAPP;
  const row = body as Record<string, unknown>;
  const number = typeof row.whatsapp === "string" ? whatsappDigits(row.whatsapp) : "";
  const enabled = typeof row.enabled === "boolean" ? row.enabled : number.length >= 8;
  const message = typeof row.message === "string" ? row.message.trim().slice(0, MESSAGE_LIMIT) : "";
  const tooltip = typeof row.tooltip === "string" ? row.tooltip.trim().slice(0, TOOLTIP_LIMIT) : "";
  const email = typeof row.email === "string" ? row.email.trim() : "";
  return {
    enabled,
    number,
    message,
    tooltip: tooltip || EMPTY_WHATSAPP.tooltip,
    email: EMAIL.test(email) && email.length <= 254 ? email : "",
  };
}
