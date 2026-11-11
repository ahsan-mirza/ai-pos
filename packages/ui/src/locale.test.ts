import { describe, expect, it } from "vitest";
import { applyDocumentLocale, localize, missingArabic, setLocale } from "./locale";

describe("locale", () => {
  it("keeps english as the source and falls back when arabic is missing", () => {
    expect(localize("Checkout", "en")).toBe("Checkout");
    expect(localize("Checkout", "ar")).toBe("الدفع");
    expect(localize("USB-C Cable", "ar")).toBe("USB-C Cable");
    expect(missingArabic(["Checkout", "USB-C Cable"])).toEqual(["USB-C Cable"]);
  });

  it("sets document direction and remembers the choice on this device", () => {
    setLocale("ar");
    expect(document.documentElement.lang).toBe("ar");
    expect(document.documentElement.dir).toBe("rtl");
    expect(localize("Dashboard")).toBe("لوحة المعلومات");
    expect(localize("Scan within {seconds} seconds, then keep this page open.", "ar", { seconds: 12 })).toBe(
      "امسح خلال 12 ثانية، ثم أبقِ هذه الصفحة مفتوحة.",
    );
    setLocale("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(localize("Dashboard")).toBe("Dashboard");
    expect(localize("Plan", "ar")).toBe("الخطة");
    expect(localize("Your data", "ar")).toBe("بياناتك");
    expect(localize("Step {current} of {total}", "ar", { current: 2, total: 3 })).toBe("الخطوة 2 من 3");
    applyDocumentLocale("en");
  });
});
