import { mergeBoard, ticketAge, type KitchenTicket } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { kitchenTicketOps } from "./kitchenPrint";

function ticket(overrides: Partial<KitchenTicket> = {}): KitchenTicket {
  return {
    id: "t1",
    station_id: "s1",
    station_name: "Grill",
    print_tickets: true,
    order_id: "o1",
    sale_id: null,
    number: 12,
    label: "Table 4",
    service_type: "DINE_IN",
    status: "NEW",
    fired_at: "2026-10-21T12:00:00Z",
    started_at: null,
    ready_at: null,
    bumped_at: null,
    updated_at: "2026-10-21T12:00:00Z",
    items: [
      { id: "i1", order_item_id: "x", product_name: "Burger", quantity: 2, modifiers: [{ group_id: "g", option_id: "o", option: "No onion", price_delta_cents: 0 }], seat: 1, note: "well done", ready_at: null, voided_at: null },
      { id: "i2", order_item_id: "y", product_name: "Fries", quantity: 1, modifiers: [], seat: null, note: null, ready_at: null, voided_at: "2026-10-21T12:01:00Z" },
    ],
    ...overrides,
  };
}

describe("kitchen display", () => {
  it("ages tickets amber then red", () => {
    const fired = "2026-10-21T12:00:00Z";
    const at = (minutes: number) => Date.parse(fired) + minutes * 60_000;
    expect(ticketAge(fired, at(3), 8, 15)).toBe("fresh");
    expect(ticketAge(fired, at(8), 8, 15)).toBe("warn");
    expect(ticketAge(fired, at(20), 8, 15)).toBe("late");
  });

  it("folds polled changes into the board in firing order", () => {
    const first = ticket();
    const second = ticket({ id: "t2", fired_at: "2026-10-21T11:59:00Z" });
    const merged = mergeBoard([first], [second, { ...first, status: "READY" }]);
    expect(merged.map((item) => [item.id, item.status])).toEqual([
      ["t2", "NEW"],
      ["t1", "READY"],
    ]);
  });

  it("prints live lines with modifiers and notes, skipping voided ones", () => {
    const text = kitchenTicketOps(ticket(), new Date(2026, 9, 21, 12, 5))
      .map((op) => ("text" in op ? op.text : "left" in op ? `${op.left}|${op.right}` : ""))
      .filter(Boolean);
    expect(text).toEqual(["GRILL", "#12 Table 4|12:05", "2 × Burger  (seat 1)", "  No onion", '  "well done"']);
  });
});
