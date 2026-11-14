import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AxizTabs, nextTabId, type AxizTabDefinition } from "./AxizTabs";

afterEach(() => {
  cleanup();
});

const tabs: AxizTabDefinition[] = [
  { id: "stock", label: "Stock" },
  { id: "products", label: "Products" },
  { id: "prices", label: "Price lists" },
];

function Controlled() {
  const [active, setActive] = useState("stock");
  return <AxizTabs ariaLabel="Inventory sections" tabs={tabs} activeTab={active} onChange={setActive} />;
}

describe("nextTabId", () => {
  const ids = ["stock", "products", "prices"];

  it("moves forward and backward in reading order", () => {
    expect(nextTabId(ids, "stock", "ArrowRight", "ltr")).toBe("products");
    expect(nextTabId(ids, "products", "ArrowLeft", "ltr")).toBe("stock");
    expect(nextTabId(ids, "prices", "ArrowRight", "ltr")).toBe("stock");
    expect(nextTabId(ids, "stock", "ArrowLeft", "ltr")).toBe("prices");
  });

  it("reverses the arrows for Arabic", () => {
    expect(nextTabId(ids, "stock", "ArrowLeft", "rtl")).toBe("products");
    expect(nextTabId(ids, "products", "ArrowRight", "rtl")).toBe("stock");
  });

  it("jumps to the ends", () => {
    expect(nextTabId(ids, "products", "Home", "ltr")).toBe("stock");
    expect(nextTabId(ids, "products", "End", "rtl")).toBe("prices");
    expect(nextTabId(ids, "stock", "ArrowUp", "ltr")).toBeNull();
    expect(nextTabId([], "stock", "Home", "ltr")).toBeNull();
  });
});

describe("AxizTabs", () => {
  it("renders text tabs with the active underline and no pill background", () => {
    render(<AxizTabs ariaLabel="Inventory sections" tabs={tabs} activeTab="stock" />);
    const list = screen.getByRole("tablist", { name: "Inventory sections" });
    expect(list.getAttribute("aria-orientation")).toBe("horizontal");
    expect(list.className).toContain("overflow-x-auto");
    expect(list.className).toContain("w-full");
    expect(list.className).toContain("flex-nowrap");
    const stock = screen.getByRole("tab", { name: "Stock" });
    const products = screen.getByRole("tab", { name: "Products" });
    expect(stock.getAttribute("aria-selected")).toBe("true");
    expect(stock.getAttribute("data-state")).toBe("active");
    expect(stock.className).toContain("font-semibold");
    expect(stock.className).not.toContain("rounded-full");
    expect(stock.className).not.toContain("bg-accent");
    expect(stock.querySelector("[data-axiz-underline]")?.className).toContain("bg-[var(--tab-underline)]");
    expect(products.getAttribute("aria-selected")).toBe("false");
    expect(products.className).toContain("font-medium");
    expect(products.querySelector("[data-axiz-underline]")?.className).toContain("bg-transparent");
    expect(products.className).toContain("hover:text-[var(--tab-hover)]");
  });

  it("selects a tab from a click when controlled", () => {
    render(<Controlled />);
    fireEvent.click(screen.getByRole("tab", { name: "Price lists" }));
    expect(screen.getByRole("tab", { name: "Price lists" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("tab", { name: "Stock" }).getAttribute("aria-selected")).toBe("false");
  });

  it("keeps the controlled tab until the parent changes it", () => {
    const onChange = vi.fn();
    render(<AxizTabs ariaLabel="Sections" tabs={tabs} activeTab="stock" onChange={onChange} />);
    fireEvent.click(screen.getByRole("tab", { name: "Products" }));
    expect(onChange).toHaveBeenCalledWith("products");
    expect(screen.getByRole("tab", { name: "Stock" }).getAttribute("aria-selected")).toBe("true");
  });

  it("supports an uncontrolled default", () => {
    render(<AxizTabs ariaLabel="Sections" tabs={tabs} defaultTab="products" />);
    expect(screen.getByRole("tab", { name: "Products" }).getAttribute("aria-selected")).toBe("true");
    fireEvent.click(screen.getByRole("tab", { name: "Stock" }));
    expect(screen.getByRole("tab", { name: "Stock" }).getAttribute("aria-selected")).toBe("true");
  });

  it("skips disabled tabs and still shows icons, badges, and a busy tab", () => {
    const onChange = vi.fn();
    render(
      <AxizTabs
        ariaLabel="Sections"
        activeTab="stock"
        onChange={onChange}
        tabs={[
          { id: "stock", label: "Stock", icon: <span aria-hidden="true">*</span> },
          { id: "products", label: "Products", disabled: true },
          { id: "prices", label: "Price lists", badge: 4, busy: true },
          { id: "hidden", label: "Hidden", hidden: true },
        ]}
      />,
    );
    expect(screen.queryByRole("tab", { name: "Hidden" })).toBeNull();
    const stock = screen.getByRole("tab", { name: "Stock" });
    expect(stock.textContent).toContain("*");
    const prices = screen.getByRole("tab", { name: "Price lists 4" });
    expect(prices.getAttribute("aria-busy")).toBe("true");
    const products = screen.getByRole("tab", { name: "Products" });
    expect(products.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(products);
    expect(onChange).not.toHaveBeenCalled();
    stock.focus();
    fireEvent.keyDown(stock, { key: "ArrowRight" });
    expect(document.activeElement).toBe(prices);
    expect(onChange).not.toHaveBeenCalled();
  });

  it("moves focus with arrows, Home, and End without changing the selection", () => {
    render(<AxizTabs ariaLabel="Sections" tabs={tabs} defaultTab="stock" />);
    const stock = screen.getByRole("tab", { name: "Stock" });
    const products = screen.getByRole("tab", { name: "Products" });
    const prices = screen.getByRole("tab", { name: "Price lists" });
    stock.focus();
    fireEvent.keyDown(stock, { key: "ArrowRight" });
    expect(document.activeElement).toBe(products);
    expect(stock.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(products, { key: "End" });
    expect(document.activeElement).toBe(prices);
    fireEvent.keyDown(prices, { key: "Home" });
    expect(document.activeElement).toBe(stock);
    fireEvent.keyDown(stock, { key: "Enter" });
    expect(stock.getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(stock, { key: "ArrowRight" });
    fireEvent.keyDown(products, { key: " " });
    expect(products.getAttribute("aria-selected")).toBe("true");
  });

  it("follows the RTL reading direction from dir", () => {
    render(
      <div dir="rtl">
        <AxizTabs ariaLabel="Sections" tabs={tabs} activeTab="products" />
      </div>,
    );
    const products = screen.getByRole("tab", { name: "Products" });
    products.focus();
    fireEvent.keyDown(products, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(screen.getByRole("tab", { name: "Price lists" }));
    fireEvent.keyDown(screen.getByRole("tab", { name: "Price lists" }), { key: "ArrowRight" });
    expect(document.activeElement).toBe(products);
  });

  it("renders a panel and a custom link", () => {
    render(
      <AxizTabs ariaLabel="Sections" tabs={tabs} activeTab="stock">
        <p>Stock levels</p>
      </AxizTabs>,
    );
    const panel = screen.getByRole("tabpanel");
    expect(panel.className).toContain("w-full");
    expect(panel.textContent).toContain("Stock levels");
    expect(panel.getAttribute("aria-labelledby")).toBe(screen.getByRole("tab", { name: "Stock" }).id);
    expect(screen.getByRole("tab", { name: "Stock" }).getAttribute("aria-controls")).toBe(panel.id);
  });

  it("lets the parent render the tab as a link", () => {
    render(
      <AxizTabs
        ariaLabel="Sections"
        tabs={[{ id: "/inventory/stock", label: "Stock", href: "/inventory/stock" }]}
        activeTab="/inventory/stock"
        renderTab={({ tabProps }) => <a href="/inventory/stock" {...tabProps} />}
      />,
    );
    const stock = screen.getByRole("tab", { name: "Stock" });
    expect(stock.tagName).toBe("A");
    expect(stock.getAttribute("href")).toBe("/inventory/stock");
    expect(stock.querySelector("[data-axiz-underline]")).not.toBeNull();
  });

  it("renders an empty list without throwing", () => {
    render(<AxizTabs ariaLabel="Sections" tabs={[]} />);
    expect(screen.getByRole("tablist", { name: "Sections" }).querySelectorAll("[role='tab']")).toHaveLength(0);
  });

  it("updates when the tab list changes", () => {
    const { rerender } = render(<AxizTabs ariaLabel="Sections" tabs={tabs.slice(0, 1)} activeTab="stock" />);
    expect(screen.getAllByRole("tab")).toHaveLength(1);
    rerender(<AxizTabs ariaLabel="Sections" tabs={tabs} activeTab="prices" />);
    expect(screen.getAllByRole("tab")).toHaveLength(3);
    expect(screen.getByRole("tab", { name: "Price lists" }).getAttribute("aria-selected")).toBe("true");
  });

  it("keeps the row from wrapping and marks the focus outline token", () => {
    render(
      <AxizTabs
        ariaLabel="Sections"
        inset="page"
        tabs={Array.from({ length: 12 }, (_, index) => ({ id: `tab-${index}`, label: `Section ${index + 1}` }))}
        activeTab="tab-0"
      />,
    );
    const list = screen.getByRole("tablist");
    expect(list.className).toContain("overflow-x-auto");
    expect(list.className).not.toContain("px-4");
    const tab = screen.getByRole("tab", { name: "Section 1" });
    expect(tab.className).toContain("whitespace-nowrap");
    expect(tab.className).toContain("flex-1");
    expect(tab.className).toContain("shrink-0");
    const underline = tab.querySelector("[data-axiz-underline]");
    expect(underline?.className).toContain("inset-x-0");
    expect(underline?.parentElement?.className).toContain("inline-flex");
    expect(underline?.parentElement?.className).toContain("h-full");
    expect(tab.className).toContain("outline-[var(--tab-focus)]");
  });
});
