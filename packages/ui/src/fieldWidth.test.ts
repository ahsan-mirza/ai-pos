import { describe, expect, it } from "vitest";
import { fieldClass, inferFieldWidth } from "./fieldWidth";

describe("field widths", () => {
  it("names each shared size", () => {
    expect(fieldClass("sm")).toBe("field-sm");
    expect(fieldClass("date")).toBe("field-date");
    expect(fieldClass("phone")).toBe("field-phone");
    expect(fieldClass("md")).toBe("field-md");
    expect(fieldClass("lg")).toBe("field-lg");
    expect(fieldClass("file")).toBe("field-file");
    expect(fieldClass("xl")).toBe("field-xl");
    expect(fieldClass("fluid")).toBe("field-fluid");
  });

  it("matches the control to a width", () => {
    expect(inferFieldWidth({ type: "number" })).toBe("sm");
    expect(inferFieldWidth({ inputMode: "decimal" })).toBe("sm");
    expect(inferFieldWidth({ label: "Purchase price (AED)" })).toBe("sm");
    expect(inferFieldWidth({ type: "date" })).toBe("date");
    expect(inferFieldWidth({ type: "datetime-local" })).toBe("date");
    expect(inferFieldWidth({ type: "tel" })).toBe("phone");
    expect(inferFieldWidth({ type: "search" })).toBe("md");
    expect(inferFieldWidth({ type: "email" })).toBe("lg");
    expect(inferFieldWidth({ type: "text", label: "Transfer reference" })).toBe("lg");
    expect(inferFieldWidth({ type: "password" })).toBe("lg");
    expect(inferFieldWidth({ type: "file" })).toBe("file");
    expect(inferFieldWidth({ multiline: true, label: "Note" })).toBe("xl");
    expect(inferFieldWidth({ type: "checkbox" })).toBe("fluid");
    expect(inferFieldWidth({ type: "radio" })).toBe("fluid");
  });
});
