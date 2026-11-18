import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { HardwareCategoriesPage } from "./CategoriesPage";
import { HardwareProductsPage } from "./ProductsPage";

const { get, page, role } = vi.hoisted(() => ({
  get: vi.fn(),
  page: vi.fn(),
  role: { current: "ADMIN" },
}));

vi.mock("../../lib/api", () => ({
  api: {
    get: (...args: unknown[]) => get(...args),
    page: (...args: unknown[]) => page(...args),
    post: vi.fn(),
    put: vi.fn(),
    del: vi.fn(),
  },
  consoleUpload: vi.fn(),
  errorText: (caught: unknown, fallback: string) => (caught instanceof Error && caught.message ? caught.message : fallback),
}));

vi.mock("../../lib/session", () => ({
  useSession: () => ({
    operator: { id: "op", email: "ops@axizpos.com", full_name: "Ops", role: role.current, is_active: true, last_login_at: null },
    status: "signed-in",
    signIn: vi.fn(),
    signOut: vi.fn(),
  }),
}));

afterEach(() => {
  cleanup();
  role.current = "ADMIN";
});

describe("hardware catalogue console", () => {
  it("lists categories from the API and lets an admin create one", async () => {
    get.mockResolvedValue([{ id: "c1", name: "Printers", slug: "printers", description: "", image_url: null, thumb_url: null, image_alt: "", display_order: 1, is_active: true }]);
    render(
      <MemoryRouter>
        <HardwareCategoriesPage />
      </MemoryRouter>,
    );
    expect(await screen.findByText("Printers")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New category" })).toBeTruthy();
  });

  it("hides catalogue edits from support", async () => {
    role.current = "SUPPORT";
    page.mockResolvedValue({ rows: [], total: 0 });
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<HardwareProductsPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("No products")).toBeTruthy();
    expect(screen.queryByText("New product")).toBeNull();
  });

  it("shows an API error instead of an empty catalogue", async () => {
    get.mockRejectedValue(new Error("Registry unavailable"));
    render(
      <MemoryRouter>
        <HardwareCategoriesPage />
      </MemoryRouter>,
    );
    expect((await screen.findByRole("alert")).textContent).toContain("Registry unavailable");
  });
});
