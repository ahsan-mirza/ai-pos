import { acceptBusinessSettings, businessIdentityError, type BusinessSettings } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";

function row(patch: Partial<BusinessSettings> = {}): BusinessSettings {
  return {
    currency: "AED",
    supported_currencies: ["AED"],
    updated_at: "2026-11-22T20:15:00Z",
    updated_by_name: "Portion Owner",
    country: "AE",
    location: "Deira",
    legal_name: "Portion Trading",
    entitlement_revision: 11,
    timezone: "Asia/Dubai",
    ...patch,
  };
}

describe("business identity sync", () => {
  it("rejects an empty legal name and an overlong location", () => {
    expect(businessIdentityError({ legalName: "  ", legalNameAr: "", location: "" })).toBe("Enter the legal name.");
    expect(businessIdentityError({ legalName: "Portion", legalNameAr: "", location: "x".repeat(121) })).toMatch(/120/);
    expect(businessIdentityError({ legalName: "Portion", legalNameAr: "", location: "Deira" })).toBeNull();
  });

  it("keeps country and location and refuses a stale or empty snapshot", () => {
    const current = row();
    expect(current.country).toBe("AE");
    expect(current.location).toBe("Deira");
    expect(acceptBusinessSettings(current, row({ entitlement_revision: 10, legal_name: "Older", updated_at: "2026-11-22T21:00:00Z" }))).toBe(false);
    expect(acceptBusinessSettings(current, row({ updated_at: "" }))).toBe(false);
    expect(acceptBusinessSettings(current, row({ entitlement_revision: 12, legal_name: "Newer", updated_at: "2026-11-22T21:00:00Z" }))).toBe(true);
  });
});
