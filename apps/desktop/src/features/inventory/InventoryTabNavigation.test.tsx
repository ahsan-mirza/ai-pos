import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { InventoryTabNavigation } from "./InventoryTabNavigation";
import type { InventoryTab } from "./tabs";

const selling: InventoryTab[] = [
  ["stock", "Stock"],
  ["products", "Products"],
  ["pricing", "Pricing"],
  ["price-lists", "Price lists"],
  ["price-changes", "Price changes"],
  ["categories", "Categories"],
  ["brands", "Brands"],
  ["units", "Units"],
  ["replenishment", "Replenishment"],
  ["counts", "Stock counts"],
  ["purchase-orders", "Purchase orders"],
  ["transfers", "Transfers"],
].map(([id, label]) => ({ id, label, permissions: [] }));

function tabMarkup(html: string, label: string): string {
  const at = html.indexOf(`>${label}<`);
  expect(at).toBeGreaterThan(-1);
  const start = html.lastIndexOf("<button", at);
  const end = html.indexOf("</button>", at);
  return html.slice(start, end);
}

function navigation(activeTab: string, tabs: readonly InventoryTab[] = selling): string {
  return renderToStaticMarkup(<InventoryTabNavigation tabs={tabs} activeTab={activeTab} onChange={() => undefined} />);
}

describe("inventory tab navigation", () => {
  it("uses a single underline row instead of pill buttons", () => {
    const html = navigation("stock");
    expect(html).toContain('role="tablist"');
    expect(html).toContain('aria-label="Inventory sections"');
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("overflow-y-hidden");
    expect(html).toContain("flex-nowrap");
    expect(html).toContain("whitespace-nowrap");
    expect(html).toContain("shrink-0");
    expect(html).toContain("overscroll-x-contain");
    expect(html).toContain("sticky");
    expect(html).not.toContain("flex-wrap");
    expect(html).not.toContain("bg-primary-500");
    expect(html).not.toContain("rounded-xl");
    expect(html).not.toContain("ring-1");
    const stock = tabMarkup(html, "Stock");
    expect(stock).toContain('aria-selected="true"');
    expect(stock).toContain('data-state="active"');
    expect(stock).toContain("font-semibold");
    expect(stock).toContain("h-12");
    expect(stock).toContain("bg-[var(--tab-underline)]");
    expect(stock).toContain("outline-[var(--tab-focus)]");
    const products = tabMarkup(html, "Products");
    expect(products).toContain('aria-selected="false"');
    expect(products).toContain("font-medium");
    expect(products).toContain("bg-transparent");
    expect(products).toContain("hover:text-[var(--tab-hover)]");
  });

  it("follows the selected section and keeps every supplied label", () => {
    const html = navigation("transfers");
    expect(tabMarkup(html, "Transfers")).toContain('aria-selected="true"');
    expect(tabMarkup(html, "Stock")).toContain('aria-selected="false"');
    expect(html.match(/aria-selected="true"/g)).toHaveLength(1);
    for (const tab of selling) {
      expect(html).toContain(`>${tab.label}<`);
    }
  });

  it("does not add a section the page did not supply", () => {
    const html = navigation("stock", selling.slice(0, 2));
    expect(html).toContain(">Stock<");
    expect(html).toContain(">Products<");
    expect(html).not.toContain("Models");
    expect(html).not.toContain("Markdowns");
    expect(html).not.toContain("Size");
    expect(html.match(/role="tab"/g)).toHaveLength(2);
  });
});
