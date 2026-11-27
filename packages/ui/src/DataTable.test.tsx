import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { DataTable } from "./DataTable";
import { activeFilterCount } from "./FilterDrawer";
import { Pencil, Trash2 } from "lucide-react";

interface Row {
  id: string;
  name: string;
}

const rows: Row[] = [
  { id: "1", name: "Cable" },
  { id: "2", name: "Adapter" },
];

describe("row actions menu", () => {
  it("lists the row's actions from one menu and skips hidden ones", () => {
    const edit = vi.fn();
    const remove = vi.fn();
    render(
      <DataTable
        aria-label="Products"
        data={rows}
        getRowId={(row) => row.id}
        rowActionLabel={(row) => row.name}
        columns={[{ id: "name", header: "Name", accessorKey: "name" }]}
        rowActions={(row) => [
          { id: "edit", label: "Edit", icon: Pencil, onSelect: () => edit(row.id) },
          { id: "delete", label: "Delete", icon: Trash2, onSelect: () => remove(row.id), hidden: row.id === "2", tone: "danger" },
        ]}
      />,
    );
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Actions for Cable" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Delete" }));
    expect(remove).toHaveBeenCalledWith("1");
    expect(edit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Actions for Adapter" }));
    expect(screen.queryByRole("menuitem", { name: "Delete" })).toBeNull();
    const item = screen.getByRole("menuitem", { name: "Edit" });
    fireEvent.click(item);
    expect(edit).toHaveBeenCalledWith("2");
  });

  it("does not run a disabled action", () => {
    const edit = vi.fn();
    render(
      <DataTable
        aria-label="Products"
        data={rows.slice(0, 1)}
        getRowId={(row) => row.id}
        rowActionLabel={(row) => row.name}
        columns={[{ id: "name", header: "Name", accessorKey: "name" }]}
        rowActions={() => [{ id: "edit", label: "Edit", onSelect: edit, disabled: true }]}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Actions for Cable" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Edit" }));
    expect(edit).not.toHaveBeenCalled();
  });
});

describe("filter drawer", () => {
  it("keeps search visible, applies the drawer, and restores the selection", () => {
    function Page() {
      const [query, setQuery] = useState("");
      const [status, setStatus] = useState("all");
      const [page, setPage] = useState(3);
      return (
        <DataTable
          aria-label="Products"
          data={rows}
          getRowId={(row) => row.id}
          columns={[{ id: "name", header: "Name", accessorKey: "name" }]}
          toolbar={{
            search: { value: query, onChange: setQuery, label: "Search products", placeholder: "Search products" },
            filters: [
              {
                id: "status",
                label: "Status",
                value: status,
                clearedValue: "all",
                onChange: setStatus,
                options: [
                  { value: "all", label: "All statuses" },
                  { value: "active", label: "Active" },
                ],
              },
            ],
            onFiltersCommit: () => setPage(1),
          }}
          pagination={{ mode: "client", currentPage: page, onPageChange: setPage }}
        />
      );
    }
    render(<Page />);
    expect(screen.getByRole("searchbox", { name: "Search products" })).toBeTruthy();
    expect(screen.queryByRole("combobox", { name: "Status" })).toBeNull();
    const closeDrawer = () => {
      const closes = screen.getAllByRole("button", { name: "Close" });
      fireEvent.click(closes[closes.length - 1]);
    };
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    closeDrawer();
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.click(screen.getByRole("button", { name: /All statuses|Status/ }));
    fireEvent.click(screen.getByRole("option", { name: "Active" }));
    closeDrawer();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByRole("button", { name: /All statuses|Status/ }).textContent).toContain("All statuses");
    fireEvent.click(screen.getByRole("button", { name: /All statuses|Status/ }));
    fireEvent.click(screen.getByRole("option", { name: "Active" }));
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(screen.getByRole("button", { name: /Filters/ }).textContent).toContain("1");
    fireEvent.click(screen.getByRole("button", { name: /Filters/ }));
    expect(screen.getByRole("button", { name: /Active|Status/ }).textContent).toContain("Active");
    fireEvent.click(screen.getByRole("button", { name: "Clear all" }));
    expect(screen.getByRole("button", { name: "Filters" }).textContent).not.toContain("1");
  });
});

describe("active filter count", () => {
  it("ignores a filter sitting on its cleared value", () => {
    expect(
      activeFilterCount([
        { id: "status", label: "Status", value: "all", clearedValue: "all", onChange: () => undefined },
        { id: "brand", label: "Brand", value: "apple", onChange: () => undefined },
      ]),
    ).toBe(1);
  });
});
