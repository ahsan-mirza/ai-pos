import { describe, expect, it } from "vitest";
import { cancellationReason, cancelWarning, needsCancelApproval, sessionCancelStage } from "./cancelOrder";

describe("order cancellation", () => {
  it("requires an explanation only for Other", () => {
    expect(cancellationReason("changed_mind", "")).toBe("[changed_mind] Customer changed their mind.");
    expect(cancellationReason("duplicate", "Second ticket")).toBe("[duplicate] Second ticket");
    expect(cancellationReason("wrong_item", "")).toContain("[wrong_item]");
    expect(cancellationReason("other", "")).toBeNull();
    expect(cancellationReason("other", "no")).toBeNull();
    expect(cancellationReason("other", "Guest left")).toBe("[other] Guest left");
  });

  it("warns from the kitchen and delivery state the register already stores", () => {
    const draft = sessionCancelStage({ order_mode: "dine_in", items: [{ kitchen_status: "PENDING" }] });
    const kitchen = sessionCancelStage({ order_mode: "takeaway", items: [{ kitchen_status: "SENT_TO_KDS" }] });
    const preparing = sessionCancelStage({ order_mode: "dine_in", items: [{ kitchen_status: "SERVED" }] });
    const dispatched = sessionCancelStage({ order_mode: "delivery", items: [{ kitchen_status: "SENT_TO_KDS" }] });
    expect(draft).toBe("draft");
    expect(cancelWarning(draft)).toBeNull();
    expect(needsCancelApproval(draft)).toBe(false);
    expect(cancelWarning(kitchen)).toMatch(/kitchen/);
    expect(cancelWarning(preparing)).toMatch(/wastage/);
    expect(cancelWarning(dispatched)).toMatch(/dispatched/);
    expect(needsCancelApproval(dispatched)).toBe(true);
  });
});
