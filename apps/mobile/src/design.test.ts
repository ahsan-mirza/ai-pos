/// <reference types="jest" />
declare const __dirname: string;
declare function require(id: string): unknown;

const fs = require("node:fs") as { readFileSync(file: string, encoding: string): string };
const path = require("node:path") as { resolve(...parts: string[]): string };

import { controlHeight, palette, radius, screenPadding, touchTarget } from "@/theme/tokens";

describe("design tokens", () => {
  it("keeps the official orange and the shared control sizes", () => {
    expect(palette.primary).toBe("#F26A21");
    expect(palette.text).toBe("#222026");
    expect(controlHeight.md).toBeGreaterThanOrEqual(50);
    expect(controlHeight.md).toBeLessThanOrEqual(54);
    expect(touchTarget).toBeGreaterThanOrEqual(44);
    expect(radius.lg).toBeGreaterThanOrEqual(14);
    expect(radius.lg).toBeLessThanOrEqual(18);
    expect(screenPadding.phone).toBeGreaterThanOrEqual(20);
    expect(screenPadding.tablet).toBe(24);
  });

  it("does not put the language switch on the sign-in screen", () => {
    const source = fs.readFileSync(path.resolve(__dirname, "features/auth/LoginScreen.tsx"), "utf8");
    expect(source).not.toContain("setLocale");
    expect(source).toContain("signInSubtitle");
    expect(source).toContain("assets/icon.png");
  });
});
