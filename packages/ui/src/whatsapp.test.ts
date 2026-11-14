import { describe, expect, it } from "vitest";
import { whatsappChatUrl, whatsappClickDigits, whatsappDigits } from "./whatsapp";

describe("whatsapp click-to-chat", () => {
  it("keeps a complete international number and drops formatting", () => {
    expect(whatsappDigits("+971 50 123 4567")).toBe("971501234567");
    expect(whatsappClickDigits("+971 50 123 4567")).toBe("971501234567");
    expect(whatsappClickDigits("971501234567")).toBe("971501234567");
  });

  it("rejects a number that is not a complete international number", () => {
    expect(whatsappClickDigits("")).toBeNull();
    expect(whatsappClickDigits("12345")).toBeNull();
    expect(whatsappClickDigits("0501234567")).toBeNull();
  });

  it("builds a wa.me link and encodes the prefilled message", () => {
    const message = "Hello AxizPOS Support Team, I need assistance with my account.";
    expect(whatsappChatUrl("971501234567", message)).toBe(
      `https://wa.me/971501234567?text=${encodeURIComponent(message)}`,
    );
    expect(whatsappChatUrl("+971 50 123 4567", "  Hello  ")).toBe(
      `https://wa.me/971501234567?text=${encodeURIComponent("Hello")}`,
    );
    expect(whatsappChatUrl("971501234567", "   ")).toBe("https://wa.me/971501234567");
  });
});
