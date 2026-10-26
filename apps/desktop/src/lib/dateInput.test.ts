import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { compareIso, DateInput, displayToIso, isoToDisplay, maskDateInput } from "@ai-pos/ui";

describe("date input format", () => {
  it("shows an ISO date as DD-MM-YYYY and keeps the stored value ISO", () => {
    expect(isoToDisplay("2026-10-26")).toBe("26-10-2026");
    expect(isoToDisplay("2026-10-26T14:30:00.000Z", true)).toBe("26-10-2026 14:30");
    expect(displayToIso("26-10-2026")).toBe("2026-10-26");
    expect(displayToIso("26-10-2026 14:30", true)).toBe("2026-10-26T14:30");
    expect(displayToIso("")).toBe("");
  });

  it("masks typing and pasted ISO without accepting an impossible day", () => {
    expect(maskDateInput("2610")).toBe("26-10");
    expect(maskDateInput("26102026")).toBe("26-10-2026");
    expect(maskDateInput("2026-10-26")).toBe("26-10-2026");
    expect(maskDateInput("261020261430", true)).toBe("26-10-2026 14:30");
    expect(displayToIso("31-02-2026")).toBeNull();
    expect(displayToIso("29-02-2024")).toBe("2024-02-29");
    expect(displayToIso("26-10")).toBeNull();
  });

  it("renders DD-MM-YYYY while the calendar keeps the ISO value", () => {
    const date = renderToStaticMarkup(createElement(DateInput, { value: "2026-10-26" }));
    expect(date).toContain('type="text"');
    expect(date).toContain('value="26-10-2026"');
    expect(date).toContain('placeholder="DD-MM-YYYY"');
    expect(date).toContain('value="2026-10-26"');
    expect(date).toContain("opacity:0");

    const stamp = renderToStaticMarkup(createElement(DateInput, { value: "2026-10-26T14:30", withTime: true }));
    expect(stamp).toContain('value="26-10-2026 14:30"');
    expect(stamp).toContain('placeholder="DD-MM-YYYY HH:mm"');
  });

  it("compares date bounds without treating a time on the same day as later", () => {
    expect(compareIso("2026-10-26", "2026-10-01")).toBeGreaterThan(0);
    expect(compareIso("2026-10-26T09:00", "2026-10-26")).toBe(0);
    expect(compareIso("2026-10-26T09:00", "2026-10-26T10:00")).toBeLessThan(0);
  });
});