import { describe, expect, it } from "vitest";
import {
  API_UNAVAILABLE,
  DIFFERENT_STORE_PENDING,
  KEY_MISMATCH,
  SAME_STORE_PENDING,
  SIGNING_UNAVAILABLE,
  SYNC_ONE,
  activationNotice,
} from "./messages";

describe("activation notices", () => {
  it("uses the signing, same-store, and different-store sentences", () => {
    expect(activationNotice("entitlement_unconfigured")).toBe(SIGNING_UNAVAILABLE);
    expect(activationNotice("entitlement_key_mismatch")).toBe(KEY_MISMATCH);
    expect(activationNotice("pending_same_store")).toBe(SAME_STORE_PENDING);
    expect(activationNotice("pending_same_store", 1)).toBe(SYNC_ONE);
    expect(activationNotice("pending_different_store")).toBe(DIFFERENT_STORE_PENDING);
    expect(activationNotice("network")).toBe(API_UNAVAILABLE);
    expect(API_UNAVAILABLE).toContain("محفوظ");
  });
});
