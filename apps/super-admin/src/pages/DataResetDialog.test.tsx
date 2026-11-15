import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DataResetSection } from "./DataResetDialog";

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock("../lib/api", () => {
  class ConsoleError extends Error {
    readonly status: number;
    readonly code: string | null;
    readonly details: unknown;
    constructor(message: string, status: number, code: string | null = null, details: unknown = null) {
      super(message);
      this.status = status;
      this.code = code;
      this.details = details;
    }
  }
  return {
    ConsoleError,
    api: {
      get: (...args: unknown[]) => get(...args),
      post: (...args: unknown[]) => post(...args),
    },
    errorText: (caught: unknown, fallback: string) =>
      caught instanceof Error && caught.message ? caught.message : fallback,
  };
});

const catalog = {
  categories: [
    {
      id: "products",
      group: "Products & Inventory",
      label: "Products, stock, and catalog",
      kind: "operational",
      warning: "Stock only for one branch.",
    },
    {
      id: "sales",
      group: "Sales & Customers",
      label: "Sales, returns, customers, and loyalty",
      kind: "operational",
      warning: "",
    },
  ],
  protected: ["Owner login stays.", "Subscription invoices stay."],
};

const branches = {
  branches: [
    { id: "store-1", name: "Main", code: "M1" },
    { id: "store-2", name: "Annex", code: "A2" },
  ],
};

const preview = {
  id: "op-1",
  scope: "store",
  categories: ["products"],
  status: "PREVIEWED",
  ready: true,
  snapshot_records: 0,
  records_reset: 0,
  records_restored: 0,
  failure: null,
  expires_at: null,
  created_at: "2026-11-15T09:00:00Z",
  completed_at: null,
  restored_at: null,
  created_by: "IT Support",
  snapshot_reference: null,
  preview: {
    ready: true,
    tenant_name: "Khalid Ahmad",
    branches: [branches.branches[0]],
    categories: ["products"],
    counts: [{ table: "inventory_levels", label: "Stock quantities", category: "products", records: 12 }],
    total_records: 12,
    dependencies: [],
    required_categories: [],
    skipped_shared: [{ label: "Products and variants", reason: "Shared across branches." }],
    protected: catalog.protected,
  },
};

function historyResponse(rows: unknown[]) {
  get.mockImplementation((url: string) => {
    if (String(url).endsWith("/catalog")) return Promise.resolve(catalog);
    if (String(url).endsWith("/branches")) return Promise.resolve(branches);
    return Promise.resolve(rows);
  });
}

afterEach(() => {
  cleanup();
  get.mockReset();
  post.mockReset();
});

describe("DataResetSection", () => {
  it("shows an empty history and keeps restore disabled until a snapshot exists", async () => {
    historyResponse([]);
    render(<DataResetSection tenantId="tenant-1" tenantName="Khalid Ahmad" onChanged={() => undefined} />);
    expect(await screen.findByText("No reset snapshots yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Restore Data" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Reset Data" })).toBeTruthy();
  });

  it("shows a failed reset without offering its snapshot for restore", async () => {
    historyResponse([
      {
        ...preview,
        status: "FAILED",
        failure: "The recovery snapshot could not be created. No data was reset.",
      },
    ]);
    render(<DataResetSection tenantId="tenant-1" tenantName="Khalid Ahmad" onChanged={() => undefined} />);
    expect(await screen.findByText("The recovery snapshot could not be created. No data was reset.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Restore Data" })).toHaveProperty("disabled", true);
  });

  it("walks a single-branch reset through preview, password, and completion", async () => {
    historyResponse([]);
    post.mockImplementation((url: string) => {
      if (String(url).endsWith("/preview")) return Promise.resolve(preview);
      if (String(url).endsWith("/authorize")) return Promise.resolve({ ...preview, status: "AUTHORIZED" });
      return Promise.resolve({
        ...preview,
        status: "COMPLETED",
        records_reset: 12,
        snapshot_records: 12,
        snapshot_reference: "abc123def456",
        completed_at: "2026-11-15T09:05:00Z",
      });
    });
    render(<DataResetSection tenantId="tenant-1" tenantName="Khalid Ahmad" onChanged={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reset Data" }));
    expect(await screen.findByText("What would you like to reset?")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/I confirm this branch/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(await screen.findByText("0 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Select All" }));
    expect(screen.getByText("2 selected")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Clear All" }));
    expect(screen.getByText("0 selected")).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/Products, stock, and catalog/));
    fireEvent.click(screen.getByRole("button", { name: "Review impact" }));
    expect(await screen.findByText("Reset Preview")).toBeTruthy();
    expect(screen.getByText(/Stock quantities: 12/)).toBeTruthy();
    expect(screen.getByText(/Estimated records: 12/)).toBeTruthy();
    expect(screen.getByText(/Not included for this scope: Products and variants/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue to password" }));
    const password = screen.getByLabelText(/Console password/, { selector: "input" });
    expect(password).toHaveProperty("type", "password");
    expect(password).toHaveProperty("value", "");
    fireEvent.click(screen.getByRole("button", { name: "Show password" }));
    expect(screen.getByLabelText(/Console password/, { selector: "input" })).toHaveProperty("type", "text");
    fireEvent.change(screen.getByLabelText(/Console password/, { selector: "input" }), { target: { value: "Operator-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset data" }));
    expect(await screen.findByText("Reset completed successfully.")).toBeTruthy();
    expect(screen.getByText(/Snapshot reference: abc123def456/)).toBeTruthy();
    expect(screen.getByText(/Administrator: IT Support/)).toBeTruthy();
    const authorize = post.mock.calls.find((call) => String(call[0]).endsWith("/authorize"));
    expect(authorize?.[1]).toEqual({ password: "Operator-password-1" });
  });

  it("shows an all-branch scope and an incorrect password", async () => {
    historyResponse([]);
    post.mockImplementation((url: string, body: { password?: string; scope?: string }) => {
      if (String(url).endsWith("/preview")) {
        return Promise.resolve({
          ...preview,
          scope: body.scope,
          preview: { ...preview.preview, branches: branches.branches, total_records: 40 },
        });
      }
      return Promise.reject(new Error("The console administrator password was not accepted."));
    });
    render(<DataResetSection tenantId="tenant-1" tenantName="Khalid Ahmad" onChanged={() => undefined} />);
    fireEvent.click(await screen.findByRole("button", { name: "Reset Data" }));
    fireEvent.click(await screen.findByLabelText(/Reset all branches/));
    expect(screen.getByText(/2 branches: Main, Annex/)).toBeTruthy();
    fireEvent.click(screen.getByLabelText(/I confirm this all-branch scope/));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.click(await screen.findByLabelText(/Sales, returns/));
    fireEvent.click(screen.getByRole("button", { name: "Review impact" }));
    await screen.findByText("Reset Preview");
    fireEvent.click(screen.getByRole("button", { name: "Continue to password" }));
    fireEvent.change(screen.getByLabelText(/Console password/, { selector: "input" }), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: "Reset data" }));
    expect((await screen.findByRole("alert")).textContent).toContain("The console administrator password was not accepted.");
    await waitFor(() => expect(screen.getByLabelText(/Console password/, { selector: "input" })).toHaveProperty("value", ""));
  });

  it("restores a snapshot after a second password", async () => {
    const snapshot = {
      ...preview,
      status: "COMPLETED",
      snapshot_records: 12,
      records_reset: 12,
      snapshot_reference: "abc123def456",
      completed_at: "2026-11-15T09:05:00Z",
    };
    historyResponse([snapshot]);
    post.mockImplementation((url: string) => {
      if (String(url).endsWith("/restore/preview")) {
        return Promise.resolve({
          ...snapshot,
          records_to_restore: 12,
          conflicts: [{ table: "inventory_levels", id: "11111111-1111-1111-1111-111111111111", resolution: "left unchanged" }],
          conflict_count: 1,
        });
      }
      if (String(url).endsWith("/restore/authorize")) return Promise.resolve(snapshot);
      return Promise.resolve({ ...snapshot, status: "RESTORED", records_restored: 11, conflicts: [] });
    });
    render(<DataResetSection tenantId="tenant-1" tenantName="Khalid Ahmad" onChanged={() => undefined} />);
    const restore = await screen.findByRole("button", { name: "Restore Data" });
    expect(restore).toHaveProperty("disabled", false);
    fireEvent.click(restore);
    expect(await screen.findByText(/12 records/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Review restore" }));
    expect(await screen.findByText(/Records to restore: 12/)).toBeTruthy();
    expect(screen.getByText(/Conflicts: 1/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Continue to password" }));
    fireEvent.change(screen.getByLabelText(/Console password/, { selector: "input" }), { target: { value: "Operator-password-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Restore data" }));
    expect(await screen.findByText(/11 records restored/)).toBeTruthy();
  });
});
