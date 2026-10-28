import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import type { StoreSubscription } from "@ai-pos/shared-types";
import { CataloguePage } from "./CataloguePage";
import { HardwarePage } from "./HardwarePage";
import { PaymentsPage } from "./PaymentsPage";
import { RequestsPage } from "./RequestsPage";
import { SubscriptionsPage } from "./CommercialPage";
import { TenantsPage } from "./TenantsPage";

const page = vi.hoisted(() => vi.fn());
const get = vi.hoisted(() => vi.fn());

vi.mock("../lib/api", () => ({
  api: {
    page: (...args: unknown[]) => page(...args),
    get: (...args: unknown[]) => get(...args),
    post: vi.fn(),
  },
  consoleBlob: vi.fn(),
  errorText: (_caught: unknown, fallback: string) => fallback,
}));

vi.mock("../lib/session", () => ({
  useSession: () => ({
    operator: { id: "1", email: "ops@example.com", full_name: "Ops", role: "ADMIN" },
    status: "signed-in",
    signIn: async () => undefined,
    signOut: () => undefined,
  }),
}));

const subscription = (name: string, status: StoreSubscription["status"]): StoreSubscription => ({
  tenant_id: name,
  tenant_name: name,
  tenant_slug: name.toLowerCase(),
  plan_code: "pro",
  plan_name: "Pro",
  cycle_code: "monthly",
  cycle_name: "Monthly",
  status,
  trial_ends_at: null,
  current_period_end: null,
  practice_mode: false,
  next_recurring_fils: 1000,
  addons: [],
});

afterEach(() => {
  cleanup();
  page.mockReset();
  get.mockReset();
});

describe("console filter layout", () => {
  it("sends tenant search and status to the tenants query", async () => {
    page.mockResolvedValue({ rows: [], total: 3 });
    render(
      <MemoryRouter>
        <TenantsPage />
      </MemoryRouter>,
    );
    expect(screen.getByRole("heading", { name: "Tenants" })).toBeTruthy();
    await waitFor(() => expect(page).toHaveBeenCalled());
    fireEvent.change(screen.getByPlaceholderText("Name, subdomain or owner email"), { target: { value: "baristo" } });
    await waitFor(() => expect(page.mock.calls.some((call) => String(call[0]).includes("q=baristo"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Suspended" }));
    await waitFor(() => expect(page.mock.calls.some((call) => String(call[0]).includes("status=suspended"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Business type" }));
    fireEvent.click(await screen.findByRole("option", { name: "Restaurant" }));
    await waitFor(() =>
      expect(
        page.mock.calls.some((call) => String(call[0]).includes("status=suspended") && String(call[0]).includes("profile=restaurant")),
      ).toBe(true),
    );
  });

  it("keeps the change-request status filter on the existing endpoint", async () => {
    get.mockResolvedValue([]);
    render(
      <MemoryRouter>
        <RequestsPage />
      </MemoryRouter>,
    );
    await waitFor(() => expect(get).toHaveBeenCalledWith("/change-requests?status=PENDING"));
    fireEvent.click(screen.getByRole("button", { name: "resolved" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("/change-requests?status=RESOLVED"));
    fireEvent.click(screen.getByRole("button", { name: "all" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("/change-requests"));
  });

  it("filters subscriptions in the browser from the same loaded list", async () => {
    get.mockResolvedValue([subscription("Cafe", "active"), subscription("Market", "trialing")]);
    render(
      <MemoryRouter>
        <SubscriptionsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Cafe")).toBeTruthy();
    expect(screen.getByText("Market")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Search store or package"), { target: { value: "caf" } });
    expect(screen.getByText("Cafe")).toBeTruthy();
    expect(screen.queryByText("Market")).toBeNull();
    fireEvent.change(screen.getByPlaceholderText("Search store or package"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Subscription status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Trialing" }));
    expect(screen.queryByText("Cafe")).toBeNull();
    expect(screen.getByText("Market")).toBeTruthy();
  });

  it("loads catalogue totals from the billing, hardware, and subscription endpoints", async () => {
    get.mockImplementation((path: string) => {
      if (path === "/billing/catalog") {
        return Promise.resolve({
          plans: [{ id: "1", code: "LITE", name: "Lite", included_registers: 1, included_modules: [], monthly_fils: 100, trial_days: 14, active: true, sort_order: 0 }],
          cycles: [],
          addons: [{ id: "a", code: "extra", name: "Extra", description: "", monthly_fils: 0, one_time_fils: 0, refundable: false, active: true, module_keys: [], sort_order: 0 }],
          fees: [],
        });
      }
      if (path === "/hardware/items") return Promise.resolve([{ available: true }, { available: false }]);
      if (path === "/modules/summary") {
        return Promise.resolve({
          catalogue_total: 1,
          implemented: 1,
          not_implemented: 0,
          active_addons: 1,
          mapped_addons: 0,
          active_subscriptions: 4,
          trialing_subscriptions: 1,
          past_due_subscriptions: 0,
          canceled_subscriptions: 0,
          pending_payments: 2,
          addon_mrr_fils: 0,
        });
      }
      if (path === "/overview") {
        return Promise.resolve({ currency: "AED", mrr_fils: 250000 });
      }
      return Promise.resolve([]);
    });
    render(
      <MemoryRouter>
        <CataloguePage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Published packages")).toBeTruthy();
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Active subscriptions. Trials, deposits, and one-time fees are excluded.")).toBeTruthy();
  });

  it("sends hardware order search and payment on the orders request", async () => {
    get.mockResolvedValue([]);
    page.mockResolvedValue({ rows: [], total: 0 });
    render(
      <MemoryRouter>
        <HardwarePage />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Orders" }));
    fireEvent.change(screen.getByPlaceholderText("Search orders"), { target: { value: "HW-1" } });
    await waitFor(() => expect(page.mock.calls.some((call) => String(call[0]).includes("q=HW-1"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Payment" }));
    fireEvent.click(await screen.findByRole("option", { name: "Paid" }));
    await waitFor(() => expect(page.mock.calls.some((call) => String(call[0]).includes("payment=paid"))).toBe(true));
    fireEvent.click(screen.getByRole("button", { name: "Fulfillment" }));
    fireEvent.click(await screen.findByRole("option", { name: "Fulfilled" }));
    await waitFor(() =>
      expect(page.mock.calls.some((call) => String(call[0]).includes("payment=paid") && String(call[0]).includes("fulfillment=fulfilled"))).toBe(
        true,
      ),
    );
  });

  it("reloads receipts when the status filter changes and narrows them by search", async () => {
    get.mockImplementation((path: string) => {
      if (String(path).startsWith("/billing/transfers")) {
        return Promise.resolve([
          {
            id: "1",
            tenant_name: "Cafe",
            invoice_id: "INV-1",
            status: "pending_review",
            amount_fils: 100,
            invoice_total_fils: 100,
            currency: "AED",
            transferred_on: "2026-01-01",
            bank_reference: "REF-CAFE",
            created_at: "2026-01-01T00:00:00Z",
            decision_reason: null,
          },
          {
            id: "2",
            tenant_name: "Market",
            invoice_id: "INV-2",
            status: "pending_review",
            amount_fils: 200,
            invoice_total_fils: 200,
            currency: "AED",
            transferred_on: "2026-01-02",
            bank_reference: "REF-MARKET",
            created_at: "2026-01-02T00:00:00Z",
            decision_reason: null,
          },
        ]);
      }
      if (path === "/billing/grace") return Promise.resolve({ grace_days: 5 });
      return Promise.resolve([]);
    });
    render(
      <MemoryRouter>
        <PaymentsPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Cafe")).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("Search store, invoice, or reference"), { target: { value: "market" } });
    expect(screen.queryByText("Cafe")).toBeNull();
    expect(screen.getByText("Market")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Receipt status" }));
    fireEvent.click(await screen.findByRole("option", { name: "Approved" }));
    await waitFor(() => expect(get).toHaveBeenCalledWith("/billing/transfers?status=approved"));
  });
});
