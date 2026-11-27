import { describe, expect, it } from "vitest";
import {
  API_UNAVAILABLE,
  DIFFERENT_STORE_PENDING,
  KEY_MISMATCH,
  SAME_STORE_PENDING,
  SERVER_UNREACHABLE,
  SIGNING_UNAVAILABLE,
  SYNC_ONE,
  activationNotice,
  hideServerAddress,
  retryLabel,
  retrySeconds,
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

  it("replaces a connection error that names the server address", () => {
    expect(hideServerAddress("Could not reach http://203.0.113.10. Check the store code and the internet connection.")).toBe(
      SERVER_UNREACHABLE,
    );
    expect(hideServerAddress(SERVER_UNREACHABLE)).toBe(SERVER_UNREACHABLE);
    expect(hideServerAddress("No store is registered at that code.")).toBeNull();
    expect(SERVER_UNREACHABLE).not.toMatch(/\d{1,3}(?:\.\d{1,3}){3}/);
  });

  it("reads the activation wait and formats the remaining clock", () => {
    expect(retrySeconds("Too many activation attempts. Try again in 9:41.")).toBe(581);
    expect(retrySeconds("Too many activation attempts. Wait a few minutes and try again.")).toBe(600);
    expect(retrySeconds("Cannot reach the server.")).toBeNull();
    expect(retryLabel(581)).toBe("Too many activation attempts. Try again in 9:41.");
    expect(retryLabel(65)).toBe("Too many activation attempts. Try again in 1:05.");
  });
});
