import { describe, expect, it } from "vitest";
import { blockPharmacyOfflineSale, chargeGate, prepareBatchAfterGate } from "./checkout";
import type { ChargeRequest } from "./queue";

describe("pharmacy offline sales", () => {
  it("blocks a pharmacy register that is offline and leaves other profiles alone", () => {
    expect(blockPharmacyOfflineSale(true, true)).toMatch(/live connection/);
    expect(blockPharmacyOfflineSale(true, false)).toBeNull();
    expect(blockPharmacyOfflineSale(false, true)).toBeNull();
    expect(blockPharmacyOfflineSale(false, false)).toBeNull();
  });

  it("does not reserve an invoice number for a blocked pharmacy sale", async () => {
    let allocated = 0;
    const request = { cart: { lines: [] } } as unknown as ChargeRequest;
    const blocked = await prepareBatchAfterGate(null, request, {
      pharmacyCatalog: true,
      offline: true,
      subscriptionLocked: false,
      profileReady: true,
    }, async () => {
      allocated += 1;
      return "ACCEPT-ACC2-000002";
    });
    expect(blocked).toEqual({ rejected: expect.stringMatching(/live connection/) });
    expect(allocated).toBe(0);
    expect(chargeGate({ pharmacyCatalog: false, offline: true, subscriptionLocked: false, profileReady: true })).toBeNull();
    expect(chargeGate({ pharmacyCatalog: false, offline: true, subscriptionLocked: false, profileReady: false })).toBeNull();
    expect(chargeGate({ pharmacyCatalog: false, offline: false, subscriptionLocked: false, profileReady: false })).toMatch(/settings/);
    expect(chargeGate({ pharmacyCatalog: true, offline: true, subscriptionLocked: false, profileReady: false })).toMatch(/settings/);
  });

  it("reserves a number only after a grocery offline sale is allowed", async () => {
    let allocated = 0;
    const request = {
      cart: { lines: [], mode: "retail", customer: null, associate: null },
      paymentMethod: "cash",
      tenders: [],
      cashierId: "cashier",
      creditApproval: null,
    } as unknown as ChargeRequest;
    const batch = await prepareBatchAfterGate(null, request, {
      pharmacyCatalog: false,
      offline: true,
      subscriptionLocked: false,
      profileReady: true,
    }, async () => {
      allocated += 1;
      return "GROCERY-GROC1-000002";
    });
    expect(allocated).toBe(1);
    expect(batch).not.toHaveProperty("rejected");
  });
});
