import { describe, expect, it } from "vitest";
import { SUPPORT_WHATSAPP_MESSAGE, landingWhatsappDigits, supportWhatsappHref } from "./supportWhatsapp";

const published = { enabled: true, whatsapp: "+971 50 123 4567", message: "Sales hello", tooltip: "Chat with Sales", email: "" };

describe("support WhatsApp", () => {
  it("uses the landing-page number and the portal support message", () => {
    expect(landingWhatsappDigits(published)).toBe("971501234567");
    expect(supportWhatsappHref(published, SUPPORT_WHATSAPP_MESSAGE)).toBe(
      `https://wa.me/971501234567?text=${encodeURIComponent(SUPPORT_WHATSAPP_MESSAGE)}`,
    );
  });

  it("does not invent a number when the landing page has none", () => {
    expect(supportWhatsappHref({ enabled: true, whatsapp: "" }, SUPPORT_WHATSAPP_MESSAGE)).toBeNull();
    expect(supportWhatsappHref({ enabled: false, whatsapp: "971501234567" }, SUPPORT_WHATSAPP_MESSAGE)).toBeNull();
    expect(supportWhatsappHref(null, SUPPORT_WHATSAPP_MESSAGE)).toBeNull();
    expect(supportWhatsappHref({ whatsapp: "12345" }, SUPPORT_WHATSAPP_MESSAGE)).toBeNull();
  });
});
