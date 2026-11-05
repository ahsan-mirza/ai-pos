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
    setLocale("en");
    expect(document.documentElement.lang).toBe("en");
    expect(document.documentElement.dir).toBe("ltr");
    expect(localize("Dashboard")).toBe("Dashboard");
    applyDocumentLocale("en");
  });
});
