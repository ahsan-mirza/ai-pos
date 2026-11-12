import type { FulfillmentBoard, SalesOrderRow } from "@ai-pos/shared-types";
import { localize, setLocale } from "@ai-pos/ui";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { FulfillmentBoardView, fulfillmentEmptyKey, type FulfillmentBoardViewProps } from "./FulfillmentBoardPage";

const row: SalesOrderRow = {
  id: "order-1",
  number: "DT-01-SO-000001",
  customer_name: "Ali Traders",
  status: "CONFIRMED",
  source: "manual",
  total_cents: 1500,
  currency: "AED",
  lines: 1,
  outstanding_units: 3,
  backordered_units: 1,
  requested_date: null,
  created_at: "2026-11-12T14:00:00Z",
};

const board: FulfillmentBoard = {
  orders_open: 13,
  orders_today: 15,
  out_for_delivery: 1,
  delivered_today: 1,
  timezone: "Asia/Dubai",
  map_configured: false,
  rows: [],
};

function props(overrides: Partial<FulfillmentBoardViewProps> = {}): FulfillmentBoardViewProps {
  return {
    board,
    boardError: null,
    view: "OPEN",
    onView: () => undefined,
    search: "",
    onSearch: () => undefined,
    storeId: "",
    onStore: () => undefined,
    branchOptions: [{ value: "store-1", label: "DT-01 · Dock" }],
    lockedStore: false,
    onClear: () => undefined,
    rows: [row],
    total: 13,
    backorders: [],
    listError: null,
    loading: false,
    page: 1,
    pageSize: 25,
    onPage: () => undefined,
    onPageSize: () => undefined,
    onRetry: () => undefined,
    onOpen: () => undefined,
    ...overrides,
  };
}

function markup(overrides: Partial<FulfillmentBoardViewProps> = {}): string {
  return renderToStaticMarkup(
    <MemoryRouter>
      <FulfillmentBoardView {...props(overrides)} />
    </MemoryRouter>,
  );
}

afterEach(() => setLocale("en"));

describe("fulfillment empty copy", () => {
  it("separates an empty open list, a branch, and a search that matches nothing", () => {
    expect(fulfillmentEmptyKey("OPEN", { query: "", storeId: "", lockedStore: false })).toBe("No open orders");
    expect(fulfillmentEmptyKey("OPEN", { query: "", storeId: "store-1", lockedStore: false })).toBe(
      "No orders in this branch.",
    );
    expect(fulfillmentEmptyKey("OPEN", { query: "DOCK", storeId: "store-1", lockedStore: false })).toBe(
      "No orders match these filters.",
    );
    expect(fulfillmentEmptyKey("DELIVERED", { query: "", storeId: "", lockedStore: false })).toBe("No sales orders here");
    expect(fulfillmentEmptyKey("backorders", { query: "", storeId: "", lockedStore: false })).toBe(
      "Nothing is waiting for stock",
    );
    expect(fulfillmentEmptyKey("OPEN", { query: "", storeId: "store-1", lockedStore: true })).toBe("No open orders");
  });
});

describe("fulfillment board", () => {
  it("shows the four KPI counts and the order the list API returned", () => {
    const html = markup();
    expect(html).toContain("Open orders");
    expect(html).toContain("Orders today");
    expect(html).toContain("Out for delivery");
    expect(html).toContain("Delivered today");
    expect(html).toContain(">13<");
    expect(html).toContain(">15<");
    expect(html).toContain("DT-01-SO-000001");
    expect(html).toContain("Ali Traders");
    expect(html).toContain("Confirmed");
    expect(html).toContain("15.00");
    expect(html).toContain("1 backordered");
    expect(html).toContain("Asia/Dubai");
  });

  it("keeps the order table full width and the unconfigured map compact", () => {
    const html = markup();
    expect(html).not.toContain("minmax(0,1.7fr)");
    expect(html).not.toContain("min-h-80");
    expect(html).toContain("lg:grid-cols-4");
    expect(html).toContain("grid-cols-2");
    expect(html).toContain("md:block");
    expect(html).toContain("md:hidden");
    expect(html).toContain("hidden lg:table-cell");
    expect(html).toContain("hidden 2xl:table-cell");
    expect(html).toContain("Map provider is not configured.");
    expect(html).toContain("overflow-x-auto");
    expect(html).toContain("Find an order");
    expect(html).toContain("All branches");
    expect(html).toContain("Showing");
    expect(html).toContain("Open");
    expect(html).toContain("Drafts");
    expect(html).toContain("Backorders");
  });

  it("reserves a taller map panel only after a provider is configured", () => {
    const html = markup({ board: { ...board, map_configured: true } });
    expect(html).toContain("min-h-72");
    expect(html).not.toContain("Map provider is not configured.");
    expect(html).not.toContain("min-h-80");
  });

  it("hides the branch selector for a user pinned to one branch", () => {
    const html = markup({ lockedStore: true, storeId: "store-1" });
    expect(html).not.toContain("All branches");
  });

  it("shows a skeleton while the first load is in flight", () => {
    const html = markup({ board: null, rows: null, loading: true, total: 0 });
    expect(html).toContain("animate-pulse");
    expect(html).not.toContain("DT-01-SO-000001");
    expect(html).not.toContain("No open orders");
  });

  it("shows an empty open list without turning it into an error", () => {
    const html = markup({ rows: [], total: 0 });
    expect(html).toContain("No open orders");
    expect(html).not.toContain("Could not load this list");
  });

  it("names a search miss and an empty branch separately", () => {
    expect(markup({ rows: [], total: 0, search: "DOCK-42" })).toContain("No orders match these filters.");
    expect(markup({ rows: [], total: 0, storeId: "store-1" })).toContain("No orders in this branch.");
    expect(markup({ rows: [], total: 0, search: "DOCK-42" })).toContain("Clear filters");
  });

  it("shows the list error and a retry instead of an empty list", () => {
    const html = markup({
      rows: null,
      total: 0,
      loading: false,
      listError: "The sales orders could not be loaded.",
      board,
    });
    expect(html).toContain("Could not load this list");
    expect(html).toContain("The sales orders could not be loaded.");
    expect(html).toContain("Try again");
    expect(html).not.toContain("No open orders");
    expect(html).toContain(">13<");
  });

  it("keeps the last KPI counts when a later board refresh fails", () => {
    const html = markup({ board, boardError: "The fulfillment board could not be loaded." });
    expect(html).toContain(">13<");
    expect(html).toContain("The fulfillment board could not be loaded.");
    expect(html).toContain("Try again");
    expect(html).toContain("DT-01-SO-000001");
  });

  it("uses an em dash when the board has never loaded", () => {
    const html = markup({
      board: null,
      boardError: "The fulfillment board could not be loaded.",
      rows: [],
      total: 0,
    });
    expect(html).toContain("Open orders</p><p class=\"mt-1 text-2xl font-semibold tabular-nums text-charcoal\">—</p>");
    expect(html).not.toContain(">13<");
  });
});

describe("fulfillment Arabic", () => {
  it("translates the board labels", () => {
    expect(localize("Fulfillment", "ar")).toBe("تنفيذ الطلبات");
    expect(localize("Map provider is not configured.", "ar")).toBe("مزود الخريطة غير مُعد.");
    expect(localize("Confirmed", "ar")).toBe("تم التأكيد");
    expect(localize("Part delivered", "ar")).toBe("توصيل جزئي");
    expect(localize("No orders match these filters.", "ar")).toBe("لا توجد طلبات تطابق عوامل التصفية.");
    expect(localize("No orders in this branch.", "ar")).toBe("لا توجد طلبات في هذا الفرع.");
    expect(localize("Could not load this list", "ar")).toBe("تعذر تحميل هذه القائمة.");
    expect(localize("Clear filters", "ar")).toBe("مسح التصفية");
    expect(localize("{count} backordered", "ar", { count: 2 })).toBe("2 مؤجل");
  });
});
