import { localize } from "@ai-pos/ui";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SupportCenter } from "./SupportCenter";
import { SUPPORT_WHATSAPP_MESSAGE } from "./supportWhatsapp";

const digits = "971501234567";

describe("SupportCenter", () => {
  it("opens the landing-page WhatsApp number in a new tab", () => {
    const html = renderToStaticMarkup(<SupportCenter collapsed={false} digits={digits} />);
    const href = `https://wa.me/${digits}?text=${encodeURIComponent(SUPPORT_WHATSAPP_MESSAGE)}`;
    expect(html).toContain(`href="${href}"`);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain("Help Center");
    expect(html).not.toContain('href="/');
  });

  it("names the collapsed rail for assistive technology", () => {
    const html = renderToStaticMarkup(<SupportCenter collapsed digits={digits} />);
    expect(html).toContain('aria-label="Help Center"');
  });

  it("translates the label and the prefilled message", () => {
    expect(localize("Help Center", "ar")).toBe("مركز المساعدة");
    const message = localize(SUPPORT_WHATSAPP_MESSAGE, "ar");
    expect(message).toContain("AxizPOS");
    expect(message).not.toBe(SUPPORT_WHATSAPP_MESSAGE);
  });

  it("does not open an internal page when the console has not published a number", () => {
    const html = renderToStaticMarkup(<SupportCenter collapsed digits={null} />);
    expect(html).toContain("Help Center");
    expect(html).toContain('type="button"');
    expect(html).toContain('aria-label="Help Center"');
    expect(html).toContain('fill="#25D366"');
    expect(html).not.toContain("<a ");
    expect(html).not.toContain("wa.me");
    expect(html).not.toContain('href="/');
  });
});
