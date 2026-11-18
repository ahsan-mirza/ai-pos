import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HardwarePage } from "./HardwarePage";
import { EMPTY_WHATSAPP } from "../whatsapp";

const product = {
  slug: "ax-15",
  name: "AX-15",
  sku: "AX-15",
  brand: "Axiz",
  model_number: "15",
  short_description: "Counter terminal",
  full_description: "",
  currency: "AED",
  display_price_fils: 189900,
  warranty_months: 12,
  stock_status: "in_stock",
  compatibility: "",
  is_featured: true,
  category_slug: "terminals",
  category_name: "Terminals",
  specifications: [],
  images: [{ url: "https://cdn.example/ax.webp", thumb_url: "https://cdn.example/ax.webp", alt: "AX-15 terminal", is_primary: true }],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hardware page", () => {
  it("shows published products and keeps a failed enquiry on screen", async () => {
    window.history.pushState({}, "", "/hardware");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/enquiries")) {
          return new Response(JSON.stringify({ error: { message: "The catalogue is busy." } }), { status: 503 });
        }
        const body = url.includes("/categories")
          ? [{ slug: "terminals", name: "Terminals", description: "", image_url: null, image_alt: "Terminals" }]
          : url.includes("/packages")
            ? []
            : [product];
        return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
      }),
    );
    render(<HardwarePage contact={EMPTY_WHATSAPP} />);
    expect((await screen.findAllByRole("heading", { name: "AX-15" })).length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Amina Ali" } });
    fireEvent.change(screen.getByLabelText("Business name"), { target: { value: "Harbour Cafe" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "amina@harbour.example" } });
    fireEvent.change(screen.getByLabelText("WhatsApp / phone"), { target: { value: "+971501234567" } });
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "Please quote one terminal for the counter." } });
    fireEvent.click(screen.getByRole("button", { name: "Request quotation" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByText("Enquiry received")).toBeNull();
  });
});
