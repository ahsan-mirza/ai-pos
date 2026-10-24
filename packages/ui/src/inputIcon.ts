import {
  AlignLeft,
  Banknote,
  Calendar,
  Hash,
  Link,
  Lock,
  Mail,
  Phone,
  ScanLine,
  Search,
  ShieldCheck,
  Store,
  Type,
  User,
  type LucideIcon,
} from "lucide-react";

export interface InputIconHints {
  type?: string;
  autoComplete?: string;
  inputMode?: string;
  name?: string;
  id?: string;
  placeholder?: string;
  label?: string;
}

/** Leading icon for a text field, chosen from its type and label. Every field gets one. */
export function inputLeadingIcon(hints: InputIconHints): LucideIcon {
  const type = (hints.type ?? "text").toLowerCase();
  const auto = (hints.autoComplete ?? "").toLowerCase();
  const mode = (hints.inputMode ?? "").toLowerCase();
  const label = (hints.label ?? "").toLowerCase();
  const blob = `${label} ${hints.name ?? ""} ${hints.id ?? ""} ${hints.placeholder ?? ""}`.toLowerCase();

  if (type === "password" || auto.includes("password") || /\b(password|pin)\b/.test(blob)) return Lock;
  if (type === "email" || auto === "email" || blob.includes("email")) return Mail;
  if (auto === "one-time-code" || /\b(otp|authenticator)\b/.test(blob)) return ShieldCheck;
  // The label wins over an example in the placeholder, so "Store name" stays a store even when the
  // example is "Al Noor Mobiles".
  if (/\bstore\b/.test(label)) return Store;
  if (type === "tel" || mode === "tel" || auto.includes("tel") || /phone|mobile|whatsapp/.test(blob)) return Phone;
  if (type === "url" || /\b(website|url)\b/.test(blob)) return Link;
  if (type === "search" || /\bsearch\b/.test(blob)) return Search;
  if (type === "date" || type === "datetime-local" || type === "time" || type === "month" || /\bdate\b/.test(blob)) return Calendar;
  if (auto === "username" || /\busername\b/.test(blob)) return User;
  if (/\bstore\b/.test(blob)) return Store;
  if (/sku|barcode|imei|serial|upc|ean/.test(blob)) return ScanLine;
  if (mode === "decimal" || /price|amount|cost|total|tax|vat|tender/.test(blob)) return Banknote;
  if (mode === "numeric" || type === "number" || /qty|quantity|count|\bunits\b/.test(blob)) return Hash;
  if (/description|note|reason|address|comment|message/.test(blob)) return AlignLeft;
  return Type;
}
