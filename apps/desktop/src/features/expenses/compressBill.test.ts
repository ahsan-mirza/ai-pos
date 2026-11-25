import { describe, expect, it } from "vitest";
import { sniffBill } from "./compressBill";

describe("bill images", () => {
  it("accepts jpeg, png and webp bytes and rejects other files", () => {
    expect(sniffBill(new Uint8Array([0xff, 0xd8, 0xff, 0x00]))).toBe("jpeg");
    expect(sniffBill(new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))).toBe("png");
    const webp = new Uint8Array(12);
    webp.set([0x52, 0x49, 0x46, 0x46], 0);
    webp.set([0x57, 0x45, 0x42, 0x50], 8);
    expect(sniffBill(webp)).toBe("webp");
    expect(sniffBill(new Uint8Array([0x25, 0x50, 0x44, 0x46]))).toBeNull();
  });
});