import {
  EMPTY_BRANDING,
  asGiftReceipt,
  packBits,
  receiptOps,
  receiptTitle,
  toMonochrome,
  type ReceiptDoc,
} from "@ai-pos/receipt";
import { DEFAULT_TAX_POLICY, zatcaQr, type ProductUpsert } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import type { CartLine } from "../checkout/cart";
import { receiptLines } from "./receipt";

const product = { id: "p1", name: "USB-C cable", price_cents: 1500, tax_category: "STANDARD" } as unknown as ProductUpsert;

function line(overrides: Partial<CartLine>): CartLine {
  return {
    lineId: crypto.randomUUID(),
    product,
    quantity: 1,
    unitType: "PIECE",
    serialValue: null,
    serialKind: null,
    groupId: null,
    listPriceCents: 1500,
    unitPriceCents: 1500,
    priceSource: "RETAIL",
    tier: "RETAIL",
    moqShortfall: 0,
    override: null,
    ...overrides,
  } as CartLine;
}

describe("receipt", () => {
  it("prints a meal as one priced line with its parts beneath", () => {
    const meal = { ...product, id: "meal", name: "Burger Meal", is_service: true } as ProductUpsert;
    const rows = receiptLines(
      [
        line({
          product: meal,
          unitPriceCents: 2800,
          listPriceCents: 2800,
          components: [
            { slot_id: "main", product_id: "burger", slot: "Main", name: "Burger", surcharge_cents: 0 },
            { slot_id: "side", product_id: "rings", slot: "Side", name: "Onion rings", surcharge_cents: 300 },
          ],
        }),
      ],
      DEFAULT_TAX_POLICY,
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ name: "Burger Meal", unitCents: 2800, detail: "+ Burger\n+ Onion rings (+3.00)" });
  });

  it("merges plain lines and keeps serialized units apart", () => {
    const policy = { ...DEFAULT_TAX_POLICY, enforced: true, standard_rate_bps: 500 };
    const rows = receiptLines(
      [
        line({ quantity: 2 }),
        line({ quantity: 1 }),
        line({ serialValue: "356789012345678", serialKind: "imei" }),
      ],
      policy,
    );
    expect(rows).toHaveLength(2);
    expect(rows[0]).toMatchObject({ quantity: 3, totalCents: 4725 });
    expect(rows[1]?.detail).toBe("IMEI 356789012345678");
  });

  it("titles follow the UAE full vs simplified rule", () => {
    expect(receiptTitle(null, null, 100).title).toBe("Receipt");
    expect(receiptTitle("100000000000003", null, 100).title).toBe("Simplified Tax Invoice");
    expect(receiptTitle("100000000000003", "100000000000004", 100).title).toBe("Tax Invoice");
    expect(receiptTitle("100000000000003", null, 1_000_001).title).toBe("Tax Invoice");
  });

  it("titles follow ZATCA: only a VAT-registered buyer gets a standard tax invoice", () => {
    expect(receiptTitle("300000000000003", null, 5_000_000, "zatca").title).toBe("Simplified Tax Invoice");
    expect(receiptTitle("300000000000003", "311111111100003", 100, "zatca").title).toBe("Tax Invoice");
  });

  it("encodes the ZATCA QR exactly like the published example", () => {
    const qr = zatcaQr({
      sellerName: "Bobs Records",
      vatNumber: "310122393500003",
      timestamp: "2022-04-25T15:30:00Z",
      totalCents: 100_000,
      vatCents: 15_000,
    });
    expect(qr).toBe("AQxCb2JzIFJlY29yZHMCDzMxMDEyMjM5MzUwMDAwMwMUMjAyMi0wNC0yNVQxNTozMDowMFoEBzEwMDAuMDAFBjE1MC4wMA==");
    const arabic = zatcaQr({ sellerName: "متجر", vatNumber: "300000000000003", timestamp: "x", totalCents: 5, vatCents: 0 });
    expect(atob(arabic).charCodeAt(1)).toBe(8);
  });

  it("prints the TRN and the bilingual title", () => {
    const doc: ReceiptDoc = {
      title: "Simplified Tax Invoice",
      titleAr: "فاتورة ضريبية مبسطة",
      number: "DT-01-000001",
      issuedAt: new Date(2026, 9, 19, 9, 5),
      storeName: "Downtown",
      storeAddress: null,
      storePhone: null,
      legalName: "AI Mobiles LLC",
      legalNameAr: null,
      trn: "100000000000003",
      cashier: "Cashier",
      customer: null,
      reference: null,
      lines: [],
      subtotalCents: 0,
      taxCents: 0,
      totalCents: 0,
      tenders: [],
      changeCents: null,
      currency: "AED",
      footer: "Thanks",
    };
    const texts = receiptOps(doc).flatMap((op) => ("text" in op ? [op.text] : "right" in op ? [op.right] : []));
    expect(texts).toContain("TRN 100000000000003");
    expect(texts).toContain("فاتورة ضريبية مبسطة");
    expect(texts).toContain("2026-10-19 09:05");
  });

  it("prints a gift receipt with items and the return code but no prices", () => {
    const sale: ReceiptDoc = {
      title: "Tax Invoice",
      titleAr: null,
      number: "8A4E3F1D",
      issuedAt: new Date(2026, 9, 21, 10, 0),
      storeName: "Boutique",
      storeAddress: null,
      storePhone: null,
      legalName: null,
      legalNameAr: null,
      trn: null,
      cashier: "Sara",
      customer: null,
      reference: null,
      lines: [{ name: "Classic Tee", detail: "M · Black", quantity: 1, unitCents: 4900, totalCents: 4631 }],
      subtotalCents: 4410,
      taxCents: 221,
      totalCents: 4631,
      tenders: [{ label: "Cash", amountCents: 4631 }],
      changeCents: 0,
      currency: "AED",
      footer: "Thanks",
      qr: "tax-qr",
    };
    const ops = receiptOps(asGiftReceipt(sale, "client-sale-1", "2026-11-20"));
    const texts = ops.flatMap((op) => ("text" in op ? [op.text] : "right" in op ? [op.right] : []));
    expect(texts.join(" ")).toContain("Classic Tee");
    expect(texts.join(" ")).toContain("2026-11-20");
    expect(texts.join(" ")).not.toMatch(/46\.31|49\.00|Cash/);
    const codes = ops.flatMap((op) => (op.kind === "qr" ? [op.data] : []));
    expect(codes).toEqual(["client-sale-1"]);
  });

  it("prints the sales associate under the cashier", () => {
    const doc: ReceiptDoc = {
      title: "Receipt",
      titleAr: null,
      number: "AB12",
      issuedAt: new Date(2026, 9, 21, 10, 0),
      storeName: "Boutique",
      storeAddress: null,
      storePhone: null,
      legalName: null,
      legalNameAr: null,
      trn: null,
      cashier: "Sara",
      servedBy: "Lina",
      customer: null,
      reference: null,
      lines: [],
      subtotalCents: 0,
      taxCents: 0,
      totalCents: 0,
      tenders: [],
      changeCents: null,
      currency: "AED",
      footer: "",
    };
    const rows = receiptOps(doc).flatMap((op) => (op.kind === "row" ? [`${op.left} ${op.right}`] : []));
    expect(rows).toContain("Cashier Sara");
    expect(rows).toContain("Served by Lina");
  });

  it("prints the logo first and the business's header and footer notes", () => {
    const doc: ReceiptDoc = {
      title: "Receipt",
      titleAr: null,
      number: "DT-01-000002",
      issuedAt: new Date(2026, 9, 21, 10, 0),
      storeName: "Downtown",
      storeAddress: "Sheikh Zayed Road\nDubai",
      storePhone: "+971 4 123 4567",
      legalName: null,
      legalNameAr: null,
      trn: null,
      cashier: "Cashier",
      customer: null,
      reference: null,
      lines: [],
      subtotalCents: 0,
      taxCents: 0,
      totalCents: 0,
      tenders: [],
      changeCents: null,
      currency: "AED",
      footer: "",
      branding: {
        ...EMPTY_BRANDING,
        logo_png: "data:image/png;base64,AAAA",
        header_text: "Welcome!",
        footer_text: "Exchanges within 7 days.",
        footer_text_ar: "الاستبدال خلال 7 أيام",
        email: "hello@shop.ae",
      },
    };
    const ops = receiptOps(doc);
    expect(ops[0]).toMatchObject({ kind: "image", src: "data:image/png;base64,AAAA" });
    const texts = ops.flatMap((op) => (op.kind === "text" ? [op.text] : []));
    expect(texts).toEqual(
      expect.arrayContaining(["Sheikh Zayed Road\nDubai", "+971 4 123 4567", "hello@shop.ae", "Welcome!", "Exchanges within 7 days."]),
    );
    expect(ops.find((op) => op.kind === "text" && op.text === "الاستبدال خلال 7 أيام")).toMatchObject({ rtl: true });
    expect(texts.indexOf("Welcome!")).toBeLessThan(texts.indexOf("Exchanges within 7 days."));
  });

  it("dithers mid-grey to about half ink and thresholds line art", () => {
    const grey = new Float32Array(16 * 16).fill(128);
    const dithered = toMonochrome(grey, 16, 16, "dither");
    const inked = dithered.reduce((sum, value) => sum + value, 0);
    expect(inked).toBeGreaterThan(256 * 0.4);
    expect(inked).toBeLessThan(256 * 0.6);
    expect(toMonochrome(new Float32Array([10, 200]), 2, 1, "threshold")).toEqual(new Uint8Array([1, 0]));
  });

  it("packs pixels MSB first with black as 1", () => {
    const width = 10;
    const pixels = new Uint8ClampedArray(width * 4).fill(255);
    for (const x of [0, 9]) pixels.set([0, 0, 0, 255], x * 4);
    expect(packBits(pixels, width, 1)).toEqual([0b10000000, 0b01000000]);
  });
});
