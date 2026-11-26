import { describe, expect, it } from "vitest";

import { invoiceSeriesPreview, registerStatus, seatSummary } from "./status";

describe("register status", () => {
  it("names the four till states", () => {
    expect(registerStatus("active")).toEqual({ label: "Active", live: true });
    expect(registerStatus("offline")).toEqual({ label: "Offline", live: false });
    expect(registerStatus("pending")).toEqual({ label: "Activation pending", live: false });
    expect(registerStatus("revoked")).toEqual({ label: "Revoked", live: false });
    expect(registerStatus(undefined).label).toBe("Activation pending");
  });
});

describe("invoice series preview", () => {
  it("follows the branch and register codes", () => {
    expect(invoiceSeriesPreview("DT-01", "R01")).toBe("DT-01-R01");
    expect(invoiceSeriesPreview("downtown", "front")).toBe("DOWNTOWN-FRONT");
  });
});

describe("package seats", () => {
  it("explains a full package", () => {
    expect(seatSummary({ used: 1, limit: 1, available: 0 })).toBe(
      "This plan includes 1 register. Release an existing till or upgrade the package.",
    );
  });

  it("counts a free seat", () => {
    expect(seatSummary({ used: 1, limit: 3, available: 2 })).toBe("1 of 3 tills in use. 2 seats available.");
  });

  it("says when the package has no cap", () => {
    expect(seatSummary({ used: 4, limit: null, available: null })).toBe(
      "4 tills registered. This package does not cap registers.",
    );
  });
});
