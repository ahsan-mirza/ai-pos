import { formatMoney, type ReceiptSettings, type TaxAuthority } from "@ai-pos/shared-types";

export interface ReceiptLine {
  name: string;
  detail: string | null;
  quantity: number;
  unitCents: number;
  totalCents: number;
}

/** What the business configures in the portal (GET /api/v1/settings/receipt); every field is optional. */
export type ReceiptBranding = ReceiptSettings;

export const EMPTY_BRANDING: ReceiptBranding = {
  logo_png: null,
  header_text: null,
  header_text_ar: null,
  footer_text: null,
  footer_text_ar: null,
  email: null,
  website: null,
};

export interface ReceiptIdentity {
  storeName: string;
  storeAddress: string | null;
  storePhone: string | null;
  legalName: string | null;
  legalNameAr: string | null;
  trn: string | null;
  taxAuthority: TaxAuthority;
  branding?: ReceiptBranding | null;
}

export interface ReceiptDoc extends Omit<ReceiptIdentity, "taxAuthority"> {
  title: string;
  titleAr: string | null;
  number: string;
  issuedAt: Date;
  cashier: string;
  /** The stylist who served the customer, when it is not the cashier. */
  servedBy?: string | null;
  /** Markdown savings across the sale, printed as "You saved". */
  youSavedCents?: number | null;
  customer: string | null;
  reference: string | null;
  lines: ReceiptLine[];
  subtotalCents: number;
  taxCents: number;
  totalCents: number;
  tenders: { label: string; amountCents: number }[];
  changeCents: number | null;
  currency: string;
  /** Note for this kind of document ("Refund issued against…"); empty prints nothing. */
  footer: string;
  /** Tax-authority QR payload (ZATCA), printed under the totals. */
  qr?: string | null;
  taxAuthority?: TaxAuthority;
  /** A gift receipt: items and sizes without any price, total or payment, plus the code to return them. */
  giftReceipt?: boolean;
  /** Receipt code a gift receipt prints as a QR, so the recipient can return or exchange without the price. */
  returnCode?: string | null;
  /** "Exchange by" date on a gift receipt, e.g. "2026-11-04". */
  exchangeBy?: string | null;
}

/** The same sale as a gift receipt: no prices, totals, payments or tax QR. */
export function asGiftReceipt(doc: ReceiptDoc, returnCode: string, exchangeBy: string | null): ReceiptDoc {
  return {
    ...doc,
    title: "Gift Receipt",
    titleAr: "إيصال هدية",
    tenders: [],
    changeCents: null,
    qr: null,
    giftReceipt: true,
    returnCode,
    exchangeBy,
    footer: "A gift for you. Prices are not shown; scan the code above to exchange or return.",
  };
}

/**
 * UAE FTA: a buyer with a TRN, or a sale over AED 10,000, gets a full tax invoice (the A4 PDF).
 * ZATCA: a VAT-registered buyer gets a standard tax invoice; every other sale is simplified, whatever the total.
 */
export function receiptTitle(
  trn: string | null,
  customerTrn: string | null | undefined,
  totalCents: number,
  authority: TaxAuthority = "fta",
) {
  if (!trn) return { title: "Receipt", titleAr: "إيصال" };
  const full = authority === "zatca" ? Boolean(customerTrn) : Boolean(customerTrn) || totalCents > 1_000_000;
  if (full) return { title: "Tax Invoice", titleAr: "فاتورة ضريبية" };
  return { title: "Simplified Tax Invoice", titleAr: "فاتورة ضريبية مبسطة" };
}

export type ReceiptOp =
  | { kind: "text"; text: string; size: number; bold?: boolean; align?: "left" | "center" | "right"; rtl?: boolean }
  | { kind: "row"; left: string; right: string; size: number; bold?: boolean }
  | { kind: "rule"; dashed?: boolean }
  | { kind: "gap"; height: number }
  | { kind: "band"; text: string; size: number }
  | { kind: "qr"; data: string; size: number }
  | { kind: "image"; src: string; maxHeight: number };

function centered(text: string | null | undefined, size: number, rtl = false): ReceiptOp[] {
  const value = text?.trim();
  return value ? [{ kind: "text", text: value, size, align: "center", rtl }] : [];
}

export function receiptOps(doc: ReceiptDoc): ReceiptOp[] {
  const money = (cents: number) => formatMoney(cents, doc.currency);
  const brand = doc.branding ?? null;
  const ops: ReceiptOp[] = [];
  if (brand?.logo_png) ops.push({ kind: "image", src: brand.logo_png, maxHeight: 200 }, { kind: "gap", height: 8 });
  ops.push({ kind: "text", text: doc.legalName ?? doc.storeName, size: 30, bold: true, align: "center" });
  if (doc.legalNameAr) ops.push({ kind: "text", text: doc.legalNameAr, size: 26, align: "center", rtl: true });
  if (doc.legalName && doc.legalName !== doc.storeName) ops.push({ kind: "text", text: doc.storeName, size: 22, align: "center" });
  ops.push(...centered(doc.storeAddress, 20), ...centered(doc.storePhone, 20));
  ops.push(...centered(brand?.email, 20), ...centered(brand?.website, 20));
  if (doc.trn) {
    const label = doc.qr ? "VAT No." : "TRN";
    ops.push({ kind: "text", text: `${label} ${doc.trn}`, size: 22, bold: true, align: "center" });
  }
  if (brand?.header_text || brand?.header_text_ar) {
    ops.push({ kind: "gap", height: 6 }, ...centered(brand.header_text, 22), ...centered(brand.header_text_ar, 22, true));
  }
  ops.push({ kind: "gap", height: 10 }, { kind: "band", text: doc.title, size: 26 });
  if (doc.titleAr) ops.push({ kind: "text", text: doc.titleAr, size: 24, align: "center", rtl: true });
  ops.push(
    { kind: "gap", height: 8 },
    { kind: "row", left: "No.", right: doc.number, size: 22, bold: true },
    { kind: "row", left: "Date", right: formatIssued(doc.issuedAt), size: 20 },
    { kind: "row", left: "Cashier", right: doc.cashier, size: 20 },
  );
  if (doc.servedBy) ops.push({ kind: "row", left: "Served by", right: doc.servedBy, size: 20 });
  if (doc.giftReceipt) {
    ops.push({ kind: "rule" });
    for (const line of doc.lines) {
      ops.push({ kind: "text", text: line.name, size: 22, bold: true });
      if (line.detail) ops.push({ kind: "text", text: line.detail, size: 18 });
      ops.push({ kind: "row", left: "Qty", right: String(line.quantity), size: 22 });
    }
    ops.push({ kind: "rule" });
    if (doc.exchangeBy) ops.push({ kind: "row", left: "Exchange by", right: doc.exchangeBy, size: 22, bold: true });
    if (doc.returnCode) {
      ops.push({ kind: "gap", height: 10 }, { kind: "qr", data: doc.returnCode, size: 200 });
      ops.push({ kind: "text", text: doc.returnCode.slice(0, 8).toUpperCase(), size: 20, align: "center" });
    }
    ops.push({ kind: "gap", height: 14 }, ...centered(doc.footer, 20), { kind: "gap", height: 24 });
    return ops;
  }
  if (doc.customer) ops.push({ kind: "row", left: "Customer", right: doc.customer, size: 20 });
  if (doc.reference) ops.push({ kind: "row", left: "Against", right: doc.reference, size: 20 });
  ops.push({ kind: "rule" });
  for (const line of doc.lines) {
    ops.push({ kind: "text", text: line.name, size: 22, bold: true });
    if (line.detail) ops.push({ kind: "text", text: line.detail, size: 18 });
    ops.push({ kind: "row", left: `${line.quantity} × ${money(line.unitCents)}`, right: money(line.totalCents), size: 22 });
  }
  ops.push(
    { kind: "rule" },
    { kind: "row", left: "Subtotal excl. VAT", right: money(doc.subtotalCents), size: 22 },
    { kind: "row", left: "VAT", right: money(doc.taxCents), size: 22 },
    { kind: "row", left: "Total", right: money(doc.totalCents), size: 30, bold: true },
  );
  if (doc.youSavedCents) ops.push({ kind: "row", left: "You saved", right: money(doc.youSavedCents), size: 20 });
  if (doc.tenders.length > 0) ops.push({ kind: "rule", dashed: true });
  for (const tender of doc.tenders) ops.push({ kind: "row", left: tender.label, right: money(tender.amountCents), size: 22 });
  if (doc.changeCents !== null && doc.changeCents > 0) {
    ops.push({ kind: "row", left: "Change", right: money(doc.changeCents), size: 22, bold: true });
  }
  if (doc.qr) ops.push({ kind: "gap", height: 14 }, { kind: "qr", data: doc.qr, size: 220 });
  ops.push({ kind: "gap", height: 14 }, ...centered(doc.footer, 20));
  if (brand?.footer_text || brand?.footer_text_ar) {
    ops.push({ kind: "gap", height: 6 }, ...centered(brand.footer_text, 20), ...centered(brand.footer_text_ar, 20, true));
  }
  ops.push({ kind: "gap", height: 24 });
  return ops;
}

function formatIssued(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())} ${pad(value.getHours())}:${pad(value.getMinutes())}`;
}

/** RGBA pixels to packed 1-bit rows (MSB first, 1 = black), the layout ESC/POS GS v 0 expects. */
export function packBits(rgba: Uint8ClampedArray, width: number, height: number, threshold = 160): number[] {
  const rowBytes = Math.ceil(width / 8);
  const out = new Array<number>(rowBytes * height).fill(0);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const index = (y * width + x) * 4;
      const [red = 255, green = 255, blue = 255, opacity = 0] = rgba.subarray(index, index + 4);
      const luminance = 255 - (opacity / 255) * (255 - (0.299 * red + 0.587 * green + 0.114 * blue));
      if (luminance < threshold) {
        const byte = y * rowBytes + (x >> 3);
        out[byte] = (out[byte] ?? 0) | (0x80 >> (x & 7));
      }
    }
  }
  return out;
}
