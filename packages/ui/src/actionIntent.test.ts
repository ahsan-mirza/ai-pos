import { describe, expect, it } from "vitest";
import { actionIntentFromLabel } from "./actionIntent";

describe("actionIntentFromLabel", () => {
  it("maps payment verification and the other named actions", () => {
    expect(actionIntentFromLabel("Verify and activate")).toBe("success");
    expect(actionIntentFromLabel("Approve")).toBe("success");
    expect(actionIntentFromLabel("Confirm order")).toBe("success");
    expect(actionIntentFromLabel("Reject")).toBe("danger");
    expect(actionIntentFromLabel("Delete product")).toBe("danger");
    expect(actionIntentFromLabel("Revoke activation")).toBe("danger");
    expect(actionIntentFromLabel("Cancel")).toBe("danger");
    expect(actionIntentFromLabel("Confirm delete")).toBe("danger");
    expect(actionIntentFromLabel("Suspend")).toBe("warning");
    expect(actionIntentFromLabel("Deactivate")).toBe("warning");
    expect(actionIntentFromLabel("Reopen")).toBe("warning");
    expect(actionIntentFromLabel("Retry review")).toBe("warning");
    expect(actionIntentFromLabel("Receipt")).toBe("info");
    expect(actionIntentFromLabel("View")).toBe("info");
    expect(actionIntentFromLabel("Movement history")).toBe("info");
    expect(actionIntentFromLabel("Statement")).toBe("info");
    expect(actionIntentFromLabel("Order PDF")).toBe("info");
    expect(actionIntentFromLabel("Void")).toBe("danger");
    expect(actionIntentFromLabel("Reverse")).toBe("danger");
    expect(actionIntentFromLabel("Record bounce")).toBe("warning");
    expect(actionIntentFromLabel("Unmatch")).toBe("warning");
    expect(actionIntentFromLabel("Adjust stock")).toBe("primary");
    expect(actionIntentFromLabel("Bulk update")).toBe("primary");
    expect(actionIntentFromLabel("Edit plan")).toBe("primary");
    expect(actionIntentFromLabel("Close")).toBe("neutral");
    expect(actionIntentFromLabel("Back")).toBe("neutral");
  });
});
