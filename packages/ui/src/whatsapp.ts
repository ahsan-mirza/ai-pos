import { isValidE164 } from "./phone";

/** Digits only. Formatting characters and a leading plus are removed. */
export function whatsappDigits(value: string): string {
  return value.replace(/\D/g, "");
}

/** Digits for wa.me when the value is a complete international number. */
export function whatsappClickDigits(number: string): string | null {
  const digits = whatsappDigits(number);
  if (!isValidE164(`+${digits}`)) return null;
  return digits;
}

/** Official click-to-chat link. The visitor still sends the prefilled message. */
export function whatsappChatUrl(number: string, message: string): string {
  const digits = whatsappDigits(number);
  const text = message.trim();
  const base = `https://wa.me/${digits}`;
  return text.length > 0 ? `${base}?text=${encodeURIComponent(text)}` : base;
}
