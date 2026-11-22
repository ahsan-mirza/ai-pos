import { describe, expect, it } from "vitest";
import { currencySaveEnabled, scopeLabel, searchSettings, settingsSection, visibleSettings } from "./settingsRoutes";

describe("settings routes", () => {
  it("opens the overview and keeps old bookmarks on the new section", () => {
    expect(settingsSection("#/settings")).toBe("overview");
    expect(settingsSection("#/settings/currency")).toBe("currency");
    expect(settingsSection("#/settings/receipts")).toBe("hardware");
    expect(settingsSection("#/settings/vat")).toBe("tax");
    expect(settingsSection("#/settings/laundry-floor")).toBe("laundry-workflows");
    expect(settingsSection("#/settings/missing")).toBe("overview");
    expect(settingsSection("#/laundry/settings")).toBe("overview");
  });

  it("hides laundry and staff items unless that profile can use them", () => {
    const grocery = visibleSettings("grocery", false).map((item) => item.id);
    expect(grocery).not.toContain("laundry-services");
    expect(grocery).not.toContain("staff");
    expect(grocery).toContain("currency");
    expect(grocery).toContain("hardware");
    const laundry = visibleSettings("laundry", true).map((item) => item.id);
    expect(laundry).toEqual(expect.arrayContaining(["currency", "laundry-services", "staff", "appearance"]));
  });

  it("searches visible labels and keeps business currency out of register settings", () => {
    const routes = visibleSettings("laundry", false);
    expect(searchSettings(routes, "printer").map((item) => item.id)).toEqual(["hardware"]);
    expect(searchSettings(routes, "operations").map((item) => item.id)).toContain("workflows");
    expect(routes.find((item) => item.id === "workflows")?.short).toBe("Workflows");
    expect(routes.find((item) => item.id === "workflows")?.label).toBe("Workflows and operations");
    expect(searchSettings(routes, "exchange").map((item) => item.id)).toEqual(["currency"]);
    expect(searchSettings(routes, "").length).toBe(0);
    const currency = routes.find((item) => item.id === "currency");
    expect(currency?.group).toBe("business");
    expect(currency?.scope).toBe("business");
    expect(scopeLabel("register", false)).toBe("Register-specific");
    expect(scopeLabel("business", true)).toBe("Managed in Business Pro");
  });

  it("enables save only for a different supported currency the user may change", () => {
    expect(currencySaveEnabled("AED", "AED", true, false)).toBe(false);
    expect(currencySaveEnabled("AED", "USD", false, false)).toBe(false);
    expect(currencySaveEnabled("AED", "USD", true, true)).toBe(false);
    expect(currencySaveEnabled("AED", "USD", true, false)).toBe(true);
    expect(currencySaveEnabled("AED", "XXX", true, false)).toBe(false);
  });
});