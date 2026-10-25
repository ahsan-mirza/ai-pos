import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DEFAULT_PRIMARY, PRIMARY_PRESETS, contrastWithWhite, normalizeHex, shade } from "./theme";

describe("primary accent", () => {
  it("normalizes hex input", () => {
    expect(normalizeHex("ff4500")).toBe("#FF4500");
    expect(normalizeHex("#2563eb")).toBe("#2563EB");
    expect(normalizeHex("#abc")).toBe("#AABBCC");
    expect(normalizeHex("orange")).toBeNull();
    expect(normalizeHex("#12345")).toBeNull();
  });

  it("keeps the CSS fallback in index.css identical to the generated default scale", () => {
    const css = readFileSync(new URL("../index.css", import.meta.url), "utf8");
    for (const step of [50, 100, 200, 300, 400, 500, 600, 700]) {
      const declared = new RegExp(`--primary-${step}-rgb:\\s*([\\d ]+);`).exec(css)?.[1]?.trim();
      expect(declared, `--primary-${step}-rgb`).toBe(shade(DEFAULT_PRIMARY, step).join(" "));
    }
  });

  it("offers the six presets with brand orange as the default", () => {
    expect(PRIMARY_PRESETS.map((preset) => preset.hex)).toEqual([
      "#F26A21",
      "#2563EB",
      "#10B981",
      "#8B5CF6",
      "#F43F5E",
      "#3F3F46",
    ]);
    expect(PRIMARY_PRESETS[0]?.hex).toBe(DEFAULT_PRIMARY);
  });

  it("flags colors too light for white labels", () => {
    expect(contrastWithWhite("#3F3F46")).toBeGreaterThan(3);
    expect(contrastWithWhite("#FACC15")).toBeLessThan(3);
  });
});
