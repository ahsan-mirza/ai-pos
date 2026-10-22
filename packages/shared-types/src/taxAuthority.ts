import type { TaxAuthority } from "./settings.js";

export const TAX_AUTHORITY_LABELS: Record<TaxAuthority, { name: string; country: string; taxId: string }> = {
  fta: { name: "UAE Federal Tax Authority", country: "United Arab Emirates", taxId: "TRN" },
  zatca: { name: "ZATCA (Saudi Arabia)", country: "Saudi Arabia", taxId: "VAT number" },
};

export type EInvoiceStatus = "PENDING" | "REPORTED" | "CLEARED" | "REJECTED";

export interface EInvoice {
  id: string;
  authority: TaxAuthority;
  source_type: "sale" | "return";
  source_id: string;
  number: string;
  kind: "STANDARD" | "SIMPLIFIED";
  counter: number;
  invoice_hash: string;
  previous_hash: string;
  qr: string;
  status: EInvoiceStatus;
  submission_mode: string;
  submitted_at: string | null;
  created_at: string;
  errors: string[];
}

export interface EInvoiceList {
  items: EInvoice[];
  total: number;
}

export interface EInvoiceSummary {
  authority: TaxAuthority;
  authority_name: string;
  issues_einvoices: boolean;
  options: { code: TaxAuthority; name: string; country: string; issues_einvoices: boolean }[];
  environment: string | null;
  certificate_subject: string | null;
  certificate_expires_at: string | null;
  last_counter: number;
  last_hash: string | null;
  counts: Record<EInvoiceStatus, number>;
}

/** Saudi VAT numbers are 15 digits that start and end with 3. */
export function isSaudiVatNumber(value: string): boolean {
  return /^3\d{13}3$/.test(value);
}

/**
 * ZATCA QR payload (tags 1-5, base64 TLV), as printed by registers that may be offline. The API adds the hash,
 * signature and key tags (6-9) to the e-invoice it issues when the sale syncs. Mirrors app/tax_authority/zatca.py.
 */
export function zatcaQr(fields: {
  sellerName: string;
  vatNumber: string;
  timestamp: string;
  totalCents: number;
  vatCents: number;
}): string {
  const values = [fields.sellerName, fields.vatNumber, fields.timestamp, amount(fields.totalCents), amount(fields.vatCents)];
  const bytes: number[] = [];
  values.forEach((value, index) => {
    const encoded = utf8(value);
    if (encoded.length > 255) throw new Error(`QR tag ${index + 1} is longer than 255 bytes.`);
    bytes.push(index + 1, encoded.length, ...encoded);
  });
  return base64(bytes);
}

function utf8(value: string): number[] {
  const out: number[] = [];
  for (const char of value) {
    const code = char.codePointAt(0) ?? 0;
    if (code < 0x80) out.push(code);
    else if (code < 0x800) out.push(0xc0 | (code >> 6), 0x80 | (code & 0x3f));
    else if (code < 0x10000) out.push(0xe0 | (code >> 12), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
    else out.push(0xf0 | (code >> 18), 0x80 | ((code >> 12) & 0x3f), 0x80 | ((code >> 6) & 0x3f), 0x80 | (code & 0x3f));
  }
  return out;
}

const BASE64 = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

function base64(bytes: number[]): string {
  let out = "";
  for (let index = 0; index < bytes.length; index += 3) {
    const [a = 0, b, c] = [bytes[index], bytes[index + 1], bytes[index + 2]];
    const triple = (a << 16) | ((b ?? 0) << 8) | (c ?? 0);
    out += BASE64.charAt((triple >> 18) & 63) + BASE64.charAt((triple >> 12) & 63);
    out += b === undefined ? "=" : BASE64.charAt((triple >> 6) & 63);
    out += c === undefined ? "=" : BASE64.charAt(triple & 63);
  }
  return out;
}

function amount(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")}`;
}
