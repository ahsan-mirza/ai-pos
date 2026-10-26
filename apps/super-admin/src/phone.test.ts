import { describe, expect, it } from "vitest";
import { emailError, isValidE164, phoneError, toE164 } from "@ai-pos/ui";

describe("phone numbers", () => {
  it("turns a UAE national number with a leading zero into E.164", () => {
    expect(toE164("0501234567", "AE")).toBe("+971501234567");
  });

  it("accepts the same number without the trunk zero", () => {
    expect(toE164("501234567", "AE")).toBe("+971501234567");
  });

  it("accepts an international number and a 00 prefix", () => {
    expect(toE164("+971501234567", "AE")).toBe("+971501234567");
    expect(toE164("00971501234567", "AE")).toBe("+971501234567");
    expect(isValidE164("+971501234567")).toBe(true);
  });

  it("does not add the country code twice", () => {
    expect(toE164("+971501234567", "AE")).toBe("+971501234567");
  });

  it("rejects an incomplete number and allows an empty optional phone", () => {
    expect(toE164("123", "AE")).toBe("");
    expect(phoneError("", false)).toBeUndefined();
    expect(phoneError("", true)).toBe("Enter a phone number.");
    expect(phoneError("+971501234567", true)).toBeUndefined();
  });

  it("keeps a trunk zero for a country that does not use one as a prefix to strip blindly", () => {
    expect(toE164("0501234567", "US")).toBe("");
  });
});

describe("email", () => {
  it("allows a blank optional email and rejects a broken one", () => {
    expect(emailError("", false)).toBeUndefined();
    expect(emailError("not-an-email", false)).toBe("Please enter a valid email address.");
    expect(emailError("sara@example.com", true)).toBeUndefined();
  });
});
