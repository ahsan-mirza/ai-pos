import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PaymentCountBadge } from "./PaymentCountBadge";

describe("Payments sidebar badge", () => {
  it("renders nothing when nothing is waiting", () => {
    const { container } = render(<PaymentCountBadge count={0} collapsed={false} />);
    expect(container.textContent).toBe("");
  });

  it("shows the count beside an expanded item and on a collapsed rail", () => {
    const { rerender } = render(
      <div style={{ width: 320 }}>
        <PaymentCountBadge count={5} collapsed={false} />
      </div>,
    );
    const expanded = screen.getByText("5");
    expect(expanded.className).toContain("ml-auto");
    rerender(
      <div style={{ width: 80 }}>
        <PaymentCountBadge count={125} collapsed />
      </div>,
    );
    const collapsed = screen.getByText("99+");
    expect(collapsed.className).toContain("absolute");
  });
});
