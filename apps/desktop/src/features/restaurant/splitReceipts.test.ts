import type { ReceiptDoc } from "@ai-pos/receipt";
import { describe, expect, it } from "vitest";
import { duplicateReceipt, presentEqualSplit } from "./splitReceipts";

const bill: ReceiptDoc = {
  storeName: "Cafe",
  storeAddress: null,
  storePhone: null,
  legalName: null,
  legalNameAr: null,
  trn: null,
  title: "Receipt",
  titleAr: null,
  number: "INV-1",
  issuedAt: new Date("2026-11-22T12:00:00Z"),
  cashier: "Ada",
  customer: "Sam",
  reference: null,
  lines: [{ name: "Lunch", detail: null, quantity: 1, unitCents: 10000, totalCents: 10000 }],
  subtotalCents: 10000,
  taxCents: 500,
  totalCents: 10500,
  tenders: [{ label: "Card", amountCents: 10500 }],
  changeCents: null,
  currency: "AED",
  footer: "Thanks",
};

describe("equal split receipts", () => {
  it("keeps one combined receipt", () => {
    expect(presentEqualSplit(bill, 3, "combined")).toEqual([bill]);
  });

  it("prints one slip per share and the shares add up to the bill", () => {
    const slips = presentEqualSplit(bill, 3, "separate");
    expect(slips).toHaveLength(3);
    expect(slips.map((slip) => slip.totalCents)).toEqual([3500, 3500, 3500]);
    expect(slips.reduce((sum, slip) => sum + slip.totalCents, 0)).toBe(bill.totalCents);
    expect(slips[0]?.title).toBe("Split 1 of 3");
    expect(slips[0]?.taxCents).toBe(0);
    expect(slips[0]?.lines[0]?.name).toBe("Share of INV-1");
  });

  it("marks a reprint without changing the total", () => {
    const copy = duplicateReceipt(bill);
    expect(copy.title).toBe("DUPLICATE RECEIPT");
    expect(copy.totalCents).toBe(bill.totalCents);
    expect(copy.lines).toEqual(bill.lines);
  });
});