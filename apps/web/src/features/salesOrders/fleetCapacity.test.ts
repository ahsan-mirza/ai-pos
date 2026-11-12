import { describe, expect, it } from "vitest";
import { capacityKey, formatGrams, formatVolume } from "./fleetCapacity";
import type { FleetCapacity } from "./fleetApi";

function capacity(overrides: Partial<FleetCapacity> = {}): FleetCapacity {
  return {
    cargo_weight_grams: 400,
    cargo_volume_cm3: 1000,
    cargo_weight_incomplete: false,
    cargo_volume_incomplete: false,
    vehicle_weight_grams: 1000,
    vehicle_volume_cm3: 1_000_000,
    remaining_weight_grams: 600,
    remaining_volume_cm3: 999_000,
    weight_over: false,
    volume_over: false,
    blocked: false,
    policy: "block",
    ...overrides,
  };
}

describe("fleet capacity", () => {
  it("treats a missing vehicle limit as unknown", () => {
    expect(capacityKey(capacity({ vehicle_weight_grams: null, blocked: true }))).toBe("Vehicle capacity is unknown.");
    expect(formatGrams(null)).toBe("—");
    expect(formatVolume(null)).toBe("—");
  });

  it("warns when an item has no weight or volume", () => {
    expect(capacityKey(capacity({ cargo_weight_incomplete: true, blocked: true }))).toBe(
      "Weight or volume is missing on an item.",
    );
  });

  it("warns when the load is over the vehicle", () => {
    expect(capacityKey(capacity({ weight_over: true, blocked: true, remaining_weight_grams: -100 }))).toBe(
      "This plan is over the vehicle capacity.",
    );
  });

  it("shows the remaining load when the figures are complete", () => {
    expect(capacityKey(capacity())).toBe("Capacity is within the vehicle.");
    expect(formatGrams(1500)).toContain("1.5");
    expect(formatVolume(1000)).toContain("1");
  });
});
