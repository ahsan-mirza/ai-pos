import {
  activationBusinessCode,
  businessCodeKind,
  businessCodeLabel,
  businessCodePhrase,
  BusinessProfile,
} from "@ai-pos/shared-types";
import { localize } from "@ai-pos/ui";
import { describe, expect, it } from "vitest";

const expected: Record<string, string> = {
  [BusinessProfile.Restaurant]: "Restaurant code",
  [BusinessProfile.QuickService]: "Restaurant code",
  [BusinessProfile.Cafe]: "Café code",
  [BusinessProfile.ElectronicsWholesale]: "Store code",
  [BusinessProfile.WholesaleRetail]: "Store code",
  [BusinessProfile.RetailFashion]: "Store code",
  [BusinessProfile.Grocery]: "Store code",
};

describe("business code labels", () => {
  it("names every supported business type", () => {
    for (const [profile, label] of Object.entries(expected)) {
      expect(businessCodeLabel(profile)).toBe(label);
      expect(localize(label, "ar")).toBe(businessCodeLabel(profile, "ar"));
    }
  });

  it("keeps an unknown type on the store label", () => {
    expect(businessCodeKind(null)).toBe("store");
    expect(businessCodeKind("electronics_wholesale")).toBe("store");
    expect(businessCodePhrase("restaurant", "enter")).toBe("Enter the restaurant code.");
    expect(businessCodePhrase("cafe", "activateHint")).toContain("café code");
  });

  it("copies only the saved tenant code", () => {
    expect(activationBusinessCode("bayrut")).toBe("bayrut");
    expect(activationBusinessCode("  bayrut  ")).toBe("bayrut");
    expect(activationBusinessCode("")).toBeNull();
    expect(activationBusinessCode(null)).toBeNull();
    expect(activationBusinessCode(undefined)).toBeNull();
    expect(activationBusinessCode("bayrut")).not.toBe("MAIN");
    expect(activationBusinessCode("bayrut")).not.toBe("bayrut.example.com");
  });
});
