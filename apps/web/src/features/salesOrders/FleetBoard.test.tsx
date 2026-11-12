import { localize, setLocale } from "@ai-pos/ui";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";
import { DispatchSummary, ScheduleForm } from "./FleetBoard";
import type { DispatchPlan } from "./fleetApi";
import { dispatchPickerEmpty, overrideProblem, planProblems, scheduleProblems } from "./fleetRules";

const plan: DispatchPlan = {
  id: "plan-1",
  number: "DT-01-DSP-000001",
  store_id: "store-1",
  service_date: "2026-11-16",
  vehicle_id: "van-1",
  vehicle_code: "VAN1",
  driver_user_id: "user-1",
  driver_name: "Amina",
  status: "DRAFT",
  notes: "",
  capacity_override_by_id: null,
  confirmed_at: null,
  timezone: "Asia/Dubai",
  assignments: [],
  capacity: {
    cargo_weight_grams: 0,
    cargo_volume_cm3: 0,
    cargo_weight_incomplete: true,
    cargo_volume_incomplete: true,
    vehicle_weight_grams: null,
    vehicle_volume_cm3: null,
    remaining_weight_grams: null,
    remaining_volume_cm3: null,
    weight_over: false,
    volume_over: false,
    blocked: true,
    policy: "block",
  },
};

afterEach(() => setLocale("en"));

describe("fleet scheduling form", () => {
  it("uses the shared date field and keeps requested and promised apart", () => {
    const html = renderToStaticMarkup(<ScheduleForm zones={[]} busy={false} onSave={() => undefined} />);
    expect(html).toContain("DD-MM-YYYY");
    expect(html).toContain("Requested delivery date");
    expect(html).toContain("Promised delivery date");
    expect(html).toContain("md:grid-cols-2");
  });

  it("says when vehicle capacity is unknown", () => {
    const html = renderToStaticMarkup(<DispatchSummary plan={plan} canOverride={false} />);
    expect(html).toContain("Vehicle capacity is unknown.");
    expect(html).toContain("An authorised user can override this capacity check.");
  });

  it("explains an empty plan picker when every promised order is already assigned", () => {
    expect(dispatchPickerEmpty("2026-11-16", 2, 0)).toBe(
      "Every order promised for this date is already on a dispatch plan.",
    );
    expect(dispatchPickerEmpty("2026-11-16", 0, 0)).toBe("No orders are promised for this date.");
    expect(dispatchPickerEmpty("2026-11-16", 2, 1)).toBe("");
    expect(localize(dispatchPickerEmpty("2026-11-16", 2, 0), "ar")).not.toContain("No orders are promised");
  });

  it("rejects an empty schedule, plan, and override reason before submit", () => {
    expect(scheduleProblems({ promised: "", requested: "", start: "11:00", end: "09:00", zoneId: "", zoneActive: null })).toEqual(
      [
        "Choose a promised delivery date.",
        "The window ends at or before it starts.",
        "Choose a delivery zone.",
      ],
    );
    expect(scheduleProblems({ promised: "16-11-2026", requested: "2026-11-01", start: "09:00", end: "11:00", zoneId: "z", zoneActive: false })).toContain(
      "That delivery zone is inactive.",
    );
    expect(planProblems({ storeId: "", date: "", vehicleId: "", driverId: "", orders: 0 })).toContain(
      "Choose a branch before saving a dispatch plan.",
    );
    expect(overrideProblem("")).toBe("An override needs a reason.");
    expect(overrideProblem("Cable has no listed weight")).toBeNull();
  });

  it("has Arabic for the new scheduling copy", () => {
    expect(localize("Promised delivery date", "ar")).not.toBe("Promised delivery date");
    expect(localize("Vehicle capacity is unknown.", "ar")).not.toBe("Vehicle capacity is unknown.");
    expect(localize("Confirm dispatch", "ar")).not.toBe("Confirm dispatch");
  });
});
