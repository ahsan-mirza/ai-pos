import { describe, expect, it } from "vitest";
import { catalogGridClass, resolveDensity, resolveTheme } from "./RegisterLayout";

describe("register layout defaults", () => {
  it("uses light until this device has saved a theme", () => {
    expect(resolveTheme(null)).toBe("light");
    expect(resolveTheme("")).toBe("light");
    expect(resolveTheme("system")).toBe("light");
    expect(resolveTheme("dark")).toBe("dark");
    expect(resolveTheme("light")).toBe("light");
  });

  it("keeps a comfortable catalog unless a density was saved", () => {
    expect(resolveDensity(null)).toBe("comfortable");
    expect(resolveDensity("compact")).toBe("compact");
    expect(resolveDensity("large")).toBe("large");
    expect(catalogGridClass("large")).toContain("xl:grid-cols-3");
    expect(catalogGridClass("compact")).toContain("2xl:grid-cols-6");
  });
});
