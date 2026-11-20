import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { chooseAppVersion, versionFromFile } from "./appVersion";

describe("app version", () => {
  it("reads the version line and skips comments", () => {
    expect(versionFromFile("# note\n\n0.1.3\n")).toBe("0.1.3");
    expect(versionFromFile("not a version")).toBeNull();
    expect(versionFromFile("")).toBeNull();
  });

  it("prefers the local VERSION file, then the installed app, then package.json", () => {
    expect(chooseAppVersion("0.1.3", "0.1.1", "0.1.1")).toBe("0.1.3");
    expect(chooseAppVersion(null, "0.1.1", "0.1.0")).toBe("0.1.1");
    expect(chooseAppVersion(null, null, "0.1.0")).toBe("0.1.0");
  });

  it("matches the version checked in at apps/desktop/VERSION", () => {
    const raw = readFileSync(new URL("../../VERSION", import.meta.url), "utf8");
    expect(versionFromFile(raw)).toMatch(/^\d+\.\d+\.\d+/);
  });
});
