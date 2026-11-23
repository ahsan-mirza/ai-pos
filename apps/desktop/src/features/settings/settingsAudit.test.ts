import { describe, expect, it } from "vitest";
import { settingsAuditSummary } from "./settingsAudit";

describe("settings audit summary", () => {
  it("keeps the empty state when the settings row has no timestamp", () => {
    expect(settingsAuditSummary("", null)).toBe("No business-settings timestamp was returned. The trail is read-only.");
    expect(settingsAuditSummary("   ", "Ada")).toBe("No business-settings timestamp was returned. The trail is read-only.");
    expect(settingsAuditSummary(null, null)).toBe("No business-settings timestamp was returned. The trail is read-only.");
    expect(settingsAuditSummary("not-a-time", null)).toBe("No business-settings timestamp was returned. The trail is read-only.");
  });

  it("prints the persisted instant and actor", () => {
    const summary = settingsAuditSummary("2026-11-22T15:09:03Z", "Portion Owner");
    expect(summary).toContain("by Portion Owner");
    expect(summary).toMatch(/\d{2}-\d{2}-\d{4} \d{2}:\d{2}/);
    expect(settingsAuditSummary("2026-11-22T15:09:03Z", "  ")).not.toContain("by");
  });
});
