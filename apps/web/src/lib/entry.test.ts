import { describe, expect, it } from "vitest";
import { safeNextPath, signedInLanding, signedOutLocation } from "./entry";

const apex = "axizpos.com";
const store = "baristo.axizpos.com";

describe("sign-in return path", () => {
  it("sends a signed-out application route to the login page and remembers it", () => {
    expect(signedOutLocation("/inventory/stock", "", apex)).toBe("/login?next=%2Finventory%2Fstock");
    expect(signedOutLocation("/dashboard", "?tab=sales", apex)).toBe("/login?next=%2Fdashboard%3Ftab%3Dsales");
    expect(signedOutLocation("/", "", store)).toBe("/login?next=%2F");
  });

  it("leaves the login page, public site, and device screens where they are", () => {
    expect(signedOutLocation("/login", "", apex)).toBeNull();
    expect(signedOutLocation("/login", "?next=%2Fdashboard", apex)).toBeNull();
    expect(signedOutLocation("/", "", apex)).toBeNull();
    expect(signedOutLocation("/restaurant-pos", "", apex)).toBeNull();
    expect(signedOutLocation("/pricing", "", apex)).toBeNull();
    expect(signedOutLocation("/admin74246/overview", "", apex)).toBeNull();
    expect(signedOutLocation("/signup", "", apex)).toBeNull();
    expect(signedOutLocation("/welcome", "?handoff=once", apex)).toBeNull();
    expect(signedOutLocation("/kds", "", store)).toBeNull();
    expect(signedOutLocation("/table/4", "", store)).toBeNull();
  });

  it("returns a signed-in person to the page they asked for", () => {
    expect(signedInLanding("/login", "?next=%2Finventory%2Fstock", apex)).toBe("/inventory/stock");
    expect(signedInLanding("/login", "?next=%2Fdashboard%3Ftab%3Dsales", apex)).toBe("/dashboard?tab=sales");
    expect(signedInLanding("/login", "", apex)).toBe("/dashboard");
    expect(signedInLanding("/login", "", store)).toBe("/");
    expect(signedInLanding("/login", "?next=%2F", store)).toBe("/");
  });

  it("refuses a return path that leaves the application", () => {
    expect(safeNextPath("https://evil.example/dashboard", apex)).toBeNull();
    expect(safeNextPath("//evil.example/dashboard", apex)).toBeNull();
    expect(safeNextPath("/\\evil", apex)).toBeNull();
    expect(safeNextPath("/login", apex)).toBeNull();
    expect(safeNextPath("/signup", apex)).toBeNull();
    expect(safeNextPath("/welcome?handoff=once", apex)).toBeNull();
    expect(safeNextPath("/", apex)).toBeNull();
    expect(safeNextPath("/restaurant-pos", apex)).toBeNull();
    expect(safeNextPath("/admin74246/tenants", apex)).toBeNull();
    expect(safeNextPath("/pricing", apex)).toBeNull();
    expect(signedInLanding("/login", "?next=https%3A%2F%2Fevil.example", apex)).toBe("/dashboard");
    expect(signedInLanding("/", "", apex)).toBe("/dashboard");
  });
});
