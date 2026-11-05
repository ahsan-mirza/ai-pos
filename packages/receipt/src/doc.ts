import { formatMoney, storeReceiptLanguage, type ReceiptSettings, type TaxAuthority } from "@ai-pos/shared-types";

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
  language: "store",
  header_text: null,
  header_text_ar: null,
  footer_text: null,
  footer_text_ar: null,
  email: null,
  website: null,
};

export type SlipLanguage = "en" | "ar";

/** The language a slip actually prints. "store" uses the business country, never the cashier's screen. */
export function slipLanguage(branding: ReceiptBranding | null | undefined, country?: string | null): SlipLanguage {
  const choice = branding?.language;
  if (choice === "en" || choice === "ar") return choice;
  return storeReceiptLanguage(country);
}

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
  /** Every taxed line already included its tax, so the subtotal is the amount the customer pays. */
  vatIncluded?: boolean;
  totalCents: number;
  tenders: { label: string; amountCents: number }[];
  changeCents: number | null;
  currency: string;
  /** Note for this kind of document ("Refund issued against…"); empty prints nothing. */
  footer: string;
  /** Tax-authority QR payload (ZATCA), printed under the totals. */
  qr?: string | null;
  taxAuthority?: TaxAuthority;
  /** Printed language. Omitted slips stay English so a missing setting cannot follow the screen language. */
  language?: SlipLanguage;
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
  | { kind: "row"; left: string; right: string; size: number; bold?: boolean; rtl?: boolean }
  | { kind: "rule"; dashed?: boolean }
  | { kind: "gap"; height: number }
  | { kind: "band"; text: string; size: number; rtl?: boolean }
  | { kind: "qr"; data: string; size: number }
  | { kind: "image"; src: string; maxHeight: number };

function centered(text: string | null | undefined, size: number, rtl = false): ReceiptOp[] {
  const value = text?.trim();
  return value ? [{ kind: "text", text: value, size, align: "center", rtl }] : [];
}

const COPY = {
  en: {
    number: "No.",
    date: "Date",
    cashier: "Cashier",
    servedBy: "Served by",
    qty: "Qty",
    customer: "Customer",
    against: "Against",
    subtotal: "Subtotal",
    subtotalExcl: "Subtotal excl. VAT",
    vatIncluded: "VAT included",
    vat: "VAT",
    total: "Total",
    youSaved: "You saved",
    change: "Change",
    exchangeBy: "Exchange by",
    vatNo: "VAT No.",
    trn: "TRN",
    thankYou: "Thank you. Keep this receipt for returns and warranty.",
    refund: "Refund issued against the invoice above.",
    gift: "A gift for you. Prices are not shown; scan the code above to exchange or return.",
    test: "Printer test. Not a sale.",
  },
  ar: {
    number: "الرقم",
    date: "التاريخ",
    cashier: "أمين الصندوق",
    servedBy: "خدمك",
    qty: "الكمية",
    customer: "العميل",
    against: "مقابل",
    subtotal: "المجموع الفرعي",
    subtotalExcl: "المجموع دون الضريبة",
    vatIncluded: "ضريبة القيمة المضافة مشمولة",
    vat: "ضريبة القيمة المضافة",
    total: "الإجمالي",
    youSaved: "وفّرت",
    change: "الباقي",
    exchangeBy: "الاستبدال حتى",
    vatNo: "الرقم الضريبي",
    trn: "الرقم الضريبي",
    thankYou: "شكرًا لك. احتفظ بهذا الإيصال للمرتجعات والضمان.",
    refund: "تم إصدار الاسترداد مقابل الفاتورة أعلاه.",
    gift: "هدية لك. الأسعار غير ظاهرة؛ امسح الرمز أعلاه للاستبدال أو الإرجاع.",
    test: "اختبار الطابعة. ليست عملية بيع.",
  },
} as const;

const TENDER_AR: Record<string, string> = {
  Cash: "نقدًا",
  Card: "بطاقة",
  "Bank transfer": "تحويل بنكي",
  Transfer: "تحويل",
  "Store credit": "رصيد المتجر",
  "On account": "على الحساب",
  Cheque: "شيك",
  "Layaway deposit": "عربون التقسيط",
  "QR payment": "دفع برمز QR",
  "Loyalty points": "نقاط الولاء",
  "Trade-in credit": "رصيد الاستبدال",
  "Delivery app": "تطبيق التوصيل",
  "Pay later": "الدفع لاحقًا",
  "Gift card": "بطاقة هدية",
};

/** Built-in slip sentences. A custom note in the selected language replaces the thank-you line. */
export function slipDefault(kind: "thankYou" | "refund" | "gift" | "test", language: SlipLanguage): string {
  return COPY[language][kind];
}

function written(value: string | null | undefined): string | null {
  const text = value?.trim();
  return text ? text : null;
}

function hasArabic(text: string): boolean {
  return /[\u0600-\u06FF]/.test(text);
}

export function receiptOps(doc: ReceiptDoc): ReceiptOp[] {
  const language: SlipLanguage = doc.language === "ar" ? "ar" : "en";
  const copy = COPY[language];
  const arabic = language === "ar";
  const money = (cents: number) => formatMoney(cents, doc.currency);
  const brand = doc.branding ?? null;
  const row = (left: string, right: string, size: number, bold = false): ReceiptOp => ({
    kind: "row",
    left,
    right,
    size,
    bold,
    rtl: arabic,
  });
  const ops: ReceiptOp[] = [];
  if (brand?.logo_png) ops.push({ kind: "image", src: brand.logo_png, maxHeight: 200 }, { kind: "gap", height: 8 });
  const primary = (arabic ? written(doc.legalNameAr) : null) ?? doc.legalName ?? doc.storeName;
  ops.push({
    kind: "text",
    text: primary,
    size: 30,
    bold: true,
    align: "center",
    rtl: hasArabic(primary),
  });
  if (primary !== doc.storeName) {
    ops.push({ kind: "text", text: doc.storeName, size: 22, align: "center", rtl: hasArabic(doc.storeName) });
  }
  ops.push(...centered(doc.storeAddress, 20, hasArabic(doc.storeAddress ?? "")));
  ops.push(...centered(doc.storePhone, 20));
  ops.push(...centered(brand?.email, 20), ...centered(brand?.website, 20));
  if (doc.trn) {
    const label = doc.qr ? copy.vatNo : copy.trn;
    ops.push({ kind: "text", text: `${label} ${doc.trn}`, size: 22, bold: true, align: "center", rtl: arabic });
  }
  const header = written(arabic ? brand?.header_text_ar : brand?.header_text);
  if (header) ops.push({ kind: "gap", height: 6 }, ...centered(header, 22, arabic || hasArabic(header)));
  const title = arabic && doc.titleAr ? doc.titleAr : doc.title;
  ops.push({ kind: "gap", height: 10 }, { kind: "band", text: title, size: 26, rtl: arabic && Boolean(doc.titleAr) });
  ops.push(
    { kind: "gap", height: 8 },
    row(copy.number, doc.number, 22, true),
    row(copy.date, formatIssued(doc.issuedAt), 20),
    row(copy.cashier, doc.cashier, 20),
  );
  if (doc.servedBy) ops.push(row(copy.servedBy, doc.servedBy, 20));
  if (doc.giftReceipt) {
    ops.push({ kind: "rule" });
    for (const line of doc.lines) {
      ops.push({ kind: "text", text: line.name, size: 22, bold: true, rtl: hasArabic(line.name) });
      if (line.detail) ops.push({ kind: "text", text: line.detail, size: 18, rtl: hasArabic(line.detail) });
      ops.push(row(copy.qty, String(line.quantity), 22));
    }
    ops.push({ kind: "rule" });
    if (doc.exchangeBy) ops.push(row(copy.exchangeBy, doc.exchangeBy, 22, true));
    if (doc.returnCode) {
      ops.push({ kind: "gap", height: 10 }, { kind: "qr", data: doc.returnCode, size: 200 });
      ops.push({ kind: "text", text: doc.returnCode.slice(0, 8).toUpperCase(), size: 20, align: "center" });
    }
    const giftNote = written(arabic ? brand?.footer_text_ar : brand?.footer_text) ?? copy.gift;
    ops.push({ kind: "gap", height: 14 }, ...centered(giftNote, 20, arabic || hasArabic(giftNote)), { kind: "gap", height: 24 });
    return ops;
  }
  if (doc.customer) ops.push(row(copy.customer, doc.customer, 20));
  if (doc.reference) ops.push(row(copy.against, doc.reference, 20));
  ops.push({ kind: "rule" });
  for (const line of doc.lines) {
    ops.push({ kind: "text", text: line.name, size: 22, bold: true, rtl: hasArabic(line.name) });
    if (line.detail) ops.push({ kind: "text", text: line.detail, size: 18, rtl: hasArabic(line.detail) });
    ops.push({ kind: "row", left: `${line.quantity} × ${money(line.unitCents)}`, right: money(line.totalCents), size: 22 });
  }
  ops.push(
    { kind: "rule" },
    row(doc.vatIncluded ? copy.subtotal : copy.subtotalExcl, money(doc.subtotalCents), 22),
    row(doc.vatIncluded ? copy.vatIncluded : copy.vat, money(doc.taxCents), 22),
    row(copy.total, money(doc.totalCents), 30, true),
  );
  if (doc.youSavedCents) ops.push(row(copy.youSaved, money(doc.youSavedCents), 20));
  if (doc.tenders.length > 0) ops.push({ kind: "rule", dashed: true });
  for (const tender of doc.tenders) {
    const label = arabic ? (TENDER_AR[tender.label] ?? tender.label) : tender.label;
    ops.push(row(label, money(tender.amountCents), 22));
  }
  if (doc.changeCents !== null && doc.changeCents > 0) {
    ops.push(row(copy.change, money(doc.changeCents), 22, true));
  }
  if (doc.qr) ops.push({ kind: "gap", height: 14 }, { kind: "qr", data: doc.qr, size: 220 });
  const customFooter = written(arabic ? brand?.footer_text_ar : brand?.footer_text);
  const footer = customFooter ?? written(doc.footer) ?? copy.thankYou;
  if (footer) ops.push({ kind: "gap", height: 14 }, ...centered(footer, 20, arabic || hasArabic(footer)));
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
