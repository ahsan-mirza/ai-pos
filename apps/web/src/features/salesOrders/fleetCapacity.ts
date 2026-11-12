import type { FleetCapacity } from "./fleetApi";

/** English catalog key. Callers pass it through t(). */
export type CapacityKey =
  | "Vehicle capacity is unknown."
  | "Weight or volume is missing on an item."
  | "This plan is over the vehicle capacity."
  | "Capacity is within the vehicle.";

export function capacityKey(capacity: FleetCapacity): CapacityKey {
  if (capacity.vehicle_weight_grams == null || capacity.vehicle_volume_cm3 == null) {
    return "Vehicle capacity is unknown.";
  }
  if (capacity.cargo_weight_incomplete || capacity.cargo_volume_incomplete) {
    return "Weight or volume is missing on an item.";
  }
  if (capacity.weight_over || capacity.volume_over) return "This plan is over the vehicle capacity.";
  return "Capacity is within the vehicle.";
}

export function formatGrams(grams: number | null): string {
  if (grams == null) return "—";
  const kilos = grams / 1000;
  return `${kilos.toLocaleString(undefined, { maximumFractionDigits: 3 })} kg`;
}

export function formatVolume(cm3: number | null): string {
  if (cm3 == null) return "—";
  const litres = cm3 / 1000;
  return `${litres.toLocaleString(undefined, { maximumFractionDigits: 3 })} L`;
}
