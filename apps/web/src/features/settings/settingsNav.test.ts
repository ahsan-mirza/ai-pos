import { describe, expect, it } from "vitest";
import { automaticSettingsNav, resolveSettingsNav, settingsNavAction } from "./settingsNav";

describe("settings navigation width", () => {
  it("uses a drawer on a phone and compact labels on a laptop content width", () => {
    expect(automaticSettingsNav(390)).toBe("drawer");
    expect(automaticSettingsNav(800)).toBe("collapsed");
    expect(automaticSettingsNav(1100)).toBe("compact");
    expect(automaticSettingsNav(1366)).toBe("expanded");
  });

  it("keeps a manual collapse on a wide screen and steps down when the space runs out", () => {
    expect(resolveSettingsNav("collapsed", 1400)).toBe("collapsed");
    expect(resolveSettingsNav("expanded", 1100)).toBe("compact");
    expect(resolveSettingsNav("expanded", 400)).toBe("drawer");
    expect(resolveSettingsNav(null, 1280)).toBe("expanded");
  });

  it("offers the next narrower mode, then expands only as far as the width allows", () => {
    expect(settingsNavAction("expanded", 1400)).toEqual({ next: "compact", label: "Show compact labels" });
    expect(settingsNavAction("compact", 1400)).toEqual({ next: "collapsed", label: "Show icons only" });
    expect(settingsNavAction("collapsed", 1400)).toEqual({ next: "expanded", label: "Expand navigation" });
    expect(settingsNavAction("collapsed", 1000)).toEqual({ next: "compact", label: "Show compact labels" });
    expect(settingsNavAction("collapsed", 700)).toEqual({ next: "drawer", label: "Expand navigation" });
  });
});
