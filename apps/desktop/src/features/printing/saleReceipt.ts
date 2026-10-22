import seed from "@ai-pos/catalog/seed.json";
import { asGiftReceipt, receiptTitle, type ReceiptDoc, type ReceiptIdentity } from "@ai-pos/receipt";
import { zatcaQr, type Receipt, type SaleTender } from "@ai-pos/shared-types";
import { env } from "../../config/env";
import { terminal } from "../../config/terminal";
import type { CartLine, CartTotals } from "../checkout/cart";
import { activeStore, businessCurrency, customerTax, invoiceIdentity, receiptProfile } from "../checkout/currency";
import { posPolicy } from "../../lib/capabilities";
import type { RegisterCustomer } from "../../lib/tauri";
import { paymentLabels } from "../returns/returnMath";
import { receiptLines } from "./receipt";

const SALE_FOOTER = "Thank you. Keep this receipt for returns and warranty.";

/** Last day a gift recipient can exchange: the refund window plus the exchange-only window of the till rules. */
export function exchangeByDate(soldAt: Date = new Date()): string {
  const rules = posPolicy().returns;
  const last = new Date(soldAt.getTime() + (rules.window_days + rules.exchange_window_days) * 86_400_000);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${last.getFullYear()}-${pad(last.getMonth() + 1)}-${pad(last.getDate())}`;
}

/** Branch contact lines come from the API; the bundled seed only covers a register that has never synced. */
export function registerIdentity(): ReceiptIdentity {
  const tax = invoiceIdentity();
  const activated = terminal();
  const profile = receiptProfile();
  const store = profile?.store && profile.store.id === activeStore().id ? profile.store : null;
  const branches: { id: string; name: string; address?: string; phone?: string }[] = [seed.store, ...seed.branches];
  const fallback = store ? null : (branches.find((branch) => branch.id === env.storeId) ?? null);
  return {
    storeName: activated?.activated && activated.store_name ? activated.store_name : (store?.name ?? fallback?.name ?? seed.store.name),
    storeAddress: store ? store.address : (fallback?.address ?? null),
    storePhone: store ? store.phone : (fallback?.phone ?? null),
    legalName: tax.legalName,
    legalNameAr: tax.legalNameAr,
    trn: tax.trn,
    taxAuthority: tax.taxAuthority,
    branding: profile?.settings ?? null,
  };
}

/** ZATCA receipts carry the QR (tags 1-5) even offline; the signed tags are added to the e-invoice on sync. */
function receiptQr(identity: ReceiptIdentity, issuedAt: Date, totalCents: number, vatCents: number): string | null {
  if (identity.taxAuthority !== "zatca" || !identity.trn) return null;
  return zatcaQr({
    sellerName: identity.legalName ?? identity.storeName,
    vatNumber: identity.trn,
    timestamp: `${issuedAt.toISOString().slice(0, 19)}Z`,
    totalCents,
    vatCents,
  });
}

interface SaleReceiptInput {
  number: string;
  lines: CartLine[];
  totals: CartTotals;
  tenders: SaleTender[];
  onAccountCents: number;
  changeCents: number | null;
  cashier: string;
  servedBy?: string | null;
  customer: RegisterCustomer | null;
}

export function saleReceipt(input: SaleReceiptInput): ReceiptDoc {
  const identity = registerIdentity();
  const title = receiptTitle(identity.trn, input.customer?.trn_vat_number, input.totals.total, identity.taxAuthority);
  const issuedAt = new Date();
  const tenders = input.tenders.map((tender) => ({
    label: paymentLabels[tender.method as keyof typeof paymentLabels] ?? tender.method,
    amountCents: tender.method === "cash" && input.changeCents ? tender.amount_cents + input.changeCents : tender.amount_cents,
  }));
  if (input.onAccountCents > 0) tenders.push({ label: "On account", amountCents: input.onAccountCents });
  return {
    ...identity,
    ...title,
    number: input.number,
    issuedAt,
    cashier: input.cashier,
    servedBy: input.servedBy ?? null,
    customer: input.customer ? (input.customer.company_name ?? input.customer.name) : null,
    reference: null,
    lines: receiptLines(input.lines, customerTax(input.customer)),
    subtotalCents: input.totals.subtotal,
    taxCents: input.totals.tax,
    totalCents: input.totals.total,
    youSavedCents: input.lines.reduce((sum, line) => {
      const was = line.product.compare_at_cents;
      if (was == null || was <= line.unitPriceCents) return sum;
      return sum + (was - line.unitPriceCents) * line.quantity;
    }, 0),
    tenders,
    changeCents: input.changeCents,
    currency: businessCurrency(),
    footer: identity.branding?.footer_text || identity.branding?.footer_text_ar ? "" : SALE_FOOTER,
    qr: receiptQr(identity, issuedAt, input.totals.total, input.totals.tax),
  };
}

interface CreditNoteInput {
  number: string;
  invoice: string;
  lines: { name: string; quantity: number; unitCents: number; refundCents: number; detail: string | null }[];
  subtotalCents: number;
  taxCents: number;
  totalCents: number;
  tenders: { label: string; amountCents: number }[];
  cashier: string;
  currency: string;
}

export function creditNoteReceipt(input: CreditNoteInput): ReceiptDoc {
  const identity = registerIdentity();
  const issuedAt = new Date();
  return {
    ...identity,
    title: identity.trn ? "Tax Credit Note" : "Refund Receipt",
    titleAr: identity.trn ? "إشعار دائن ضريبي" : "إيصال استرداد",
    qr: receiptQr(identity, issuedAt, input.totalCents, input.taxCents),
    number: input.number,
    issuedAt,
    cashier: input.cashier,
    customer: null,
    reference: input.invoice,
    lines: input.lines.map((line) => ({
      name: line.name,
      detail: line.detail,
      quantity: line.quantity,
      unitCents: line.unitCents,
      totalCents: line.refundCents,
    })),
    subtotalCents: input.subtotalCents,
    taxCents: input.taxCents,
    totalCents: input.totalCents,
    tenders: input.tenders,
    changeCents: null,
    currency: input.currency,
    footer: "Refund issued against the invoice above.",
  };
}

/** A gift receipt reprinted from a looked-up sale: items and sizes only, with the sale's code as a QR. */
export function giftReceiptFromLookup(receipt: Receipt, cashier: string): ReceiptDoc {
  const soldAt = new Date(receipt.created_at);
  const { window_days, exchange_window_days = 0 } = receipt.policy;
  const doc: ReceiptDoc = {
    ...registerIdentity(),
    title: "Gift Receipt",
    titleAr: null,
    number: receipt.invoice,
    issuedAt: soldAt,
    cashier,
    customer: null,
    reference: null,
    lines: receipt.items
      .filter((item) => !item.gift_card)
      .map((item) => ({
        name: item.name,
        detail: item.variant ?? null,
        quantity: item.quantity,
        unitCents: 0,
        totalCents: 0,
      })),
    subtotalCents: 0,
    taxCents: 0,
    totalCents: 0,
    tenders: [],
    changeCents: null,
    currency: receipt.currency,
    footer: "",
  };
  const last = new Date(soldAt.getTime() + (window_days + exchange_window_days) * 86_400_000);
  return asGiftReceipt(doc, receipt.sale_id, last.toISOString().slice(0, 10));
}

/** A two-line sample for the Test print button. */
export function sampleReceipt(cashier: string): ReceiptDoc {
  const identity = registerIdentity();
  return {
    ...identity,
    ...receiptTitle(identity.trn, null, 0, identity.taxAuthority),
    number: "TEST-000000",
    issuedAt: new Date(),
    cashier,
    customer: null,
    reference: null,
    lines: [
      { name: "Test line — ignore", detail: "IMEI 000000000000000", quantity: 1, unitCents: 10_000, totalCents: 10_500 },
    ],
    subtotalCents: 10_000,
    taxCents: 500,
    totalCents: 10_500,
    tenders: [{ label: "Cash", amountCents: 10_500 }],
    changeCents: null,
    currency: businessCurrency(),
    footer: "Printer test. Not a sale.",
  };
}
