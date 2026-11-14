import { whatsappChatUrl, whatsappClickDigits, whatsappDigits } from "@ai-pos/ui";

/** Prefilled text for the Business Portal. The number comes from the public site contact. */
export const SUPPORT_WHATSAPP_MESSAGE = "Hello AxizPOS Support Team, I need assistance with my account.";

/**
 * Digits published for the marketing site, or null when that contact cannot open a chat.
 * A missing enabled flag follows the landing page: a long digit string counts as published.
 */
export function landingWhatsappDigits(body: unknown): string | null {
  if (body === null || typeof body !== "object") return null;
  const row = body as Record<string, unknown>;
  const raw = typeof row.whatsapp === "string" ? row.whatsapp : "";
  const enabled = typeof row.enabled === "boolean" ? row.enabled : whatsappDigits(raw).length >= 8;
  if (!enabled) return null;
  return whatsappClickDigits(raw);
}

/** Click-to-chat URL for the landing-page number and this portal's support message. */
export function supportWhatsappHref(body: unknown, message: string): string | null {
  const digits = landingWhatsappDigits(body);
  if (digits === null) return null;
  return whatsappChatUrl(digits, message);
}
