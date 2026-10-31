/** @vitest-environment happy-dom */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FloorBoard } from "./FloorBoard";
import { formatSeatedDuration, TableGridNode } from "./TableGridNode";
import type { FloorMatch } from "./floorStatus";

const hall: FloorMatch = {
  key: "1",
  areaId: "hall",
  search: "t-01 1",
  active: true,
  status: "ordered",
  kitchen: "preparing",
  payment: "unpaid",
};

describe("FloorBoard", () => {
  it("uses the light card tokens and keeps occupancy beside kitchen and payment", () => {
    render(
      <FloorBoard
        sections={[{ id: "hall", name: "Main Hall" }]}
        items={[hall]}
        renderItem={() => (
          <TableGridNode
            label="1"
            seats={4}
            shape="round"
            status="ordered"
            kitchen="preparing"
            payment="unpaid"
            orderProgress="in_progress"
            orderRef="#12"
            minutes={8}
            total="AED 40.00"
            onClick={() => undefined}
          />
        )}
      />,
    );
    const card = screen.getByRole("button", { name: /T-01/ });
    expect(card.getAttribute("style") ?? "").toContain("var(--table-preparing-fill)");
    expect(card.getAttribute("style") ?? "").toContain("var(--table-tone-line)");
    expect(card.className).not.toContain("#121824");
    expect(within(card).getByText("Preparing")).toBeTruthy();
    expect(screen.getByText("#12")).toBeTruthy();
    expect(screen.getByText("8m")).toBeTruthy();
    expect(formatSeatedDuration(274)).toBe("4h 34m");
    expect(formatSeatedDuration(695)).toBe("11h 35m");
    expect(formatSeatedDuration(120)).toBe("2h");
    expect(screen.getByText("AED 40.00")).toBeTruthy();
    expect(screen.getByText("Small · 4 Person")).toBeTruthy();
    expect(card.getAttribute("aria-label") ?? "").toContain("Occupied");
    expect(card.getAttribute("aria-label") ?? "").toContain("Unpaid");
    expect(card.getAttribute("aria-label") ?? "").toContain("Kitchen preparing");
    const toolbar = screen.getByTestId("table-toolbar");
    expect(toolbar.className).toContain("flex-nowrap");
    expect(toolbar.querySelector('[aria-label="Floor"]')).toBeTruthy();
    expect(toolbar.querySelector('[aria-label="Table summary"]')).toBeTruthy();
    expect(screen.getByRole("button", { name: /Main Hall/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /^Available/ }));
    expect(screen.queryByRole("button", { name: /T-01/ })).toBeNull();
  });
});
