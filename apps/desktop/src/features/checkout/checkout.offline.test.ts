import { describe, expect, it } from "vitest";
import { settleLocalSale } from "./checkout";

describe("offline sale completion", () => {
  it("treats a pending local sale as complete without waiting for the server", () => {
    expect(settleLocalSale("pending")).toEqual({
      kind: "queued",
      message: "Saved on this register. It will sync when the server is reachable.",
    });
    expect(settleLocalSale(null)).toMatchObject({ kind: "queued" });
  });

  it("keeps a sale that the server rejected or could not reach", () => {
    const rejected = settleLocalSale("rejected", "The API rejected the sale.");
    expect(rejected.kind).toBe("queued");
    if (rejected.kind === "queued") expect(rejected.message).toMatch(/Sync will retry/);
    const offline = settleLocalSale("pending", "Not synced: Could not reach the server.");
    expect(offline.kind).toBe("queued");
  });

  it("reports a sale that has already synced", () => {
    expect(settleLocalSale("synced")).toEqual({ kind: "recorded" });
  });
});
