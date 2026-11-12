import { isValidDate } from "@ai-pos/ui";

/** English catalog keys. Callers pass the result through t(). */
export function dispatchPickerEmpty(date: string, promised: number, available: number): string {
  if (available > 0) return "";
  if (promised === 0) {
    return date
      ? "No orders are promised for this date."
      : "No scheduled orders are waiting for a plan.";
  }
  return date
    ? "Every order promised for this date is already on a dispatch plan."
    : "Every scheduled order is already on a dispatch plan.";
}

export function scheduleProblems(input: {
  promised: string;
  requested: string;
  start: string;
  end: string;
  zoneId: string;
  zoneActive: boolean | null;
}): string[] {
  const problems: string[] = [];
  if (!input.promised) problems.push("Choose a promised delivery date.");
  else if (!isValidDate(input.promised)) problems.push("Enter the promised date as DD-MM-YYYY.");
  if (input.requested && !isValidDate(input.requested)) problems.push("Enter the requested date as DD-MM-YYYY.");
  if (!input.start || !input.end || input.start >= input.end) {
    problems.push("The window ends at or before it starts.");
  }
  if (!input.zoneId) problems.push("Choose a delivery zone.");
  else if (input.zoneActive === false) problems.push("That delivery zone is inactive.");
  return problems;
}

export function planProblems(input: {
  storeId: string;
  date: string;
  vehicleId: string;
  driverId: string;
  orders: number;
}): string[] {
  const problems: string[] = [];
  if (!input.storeId) problems.push("Choose a branch before saving a dispatch plan.");
  if (!input.date || !isValidDate(input.date)) problems.push("Choose a delivery date.");
  if (!input.vehicleId) problems.push("Choose a vehicle.");
  if (!input.driverId) problems.push("Choose a driver.");
  if (input.orders < 1) problems.push("Choose at least one order.");
  return problems;
}

export function measureProblem(value: string, kind: "weight" | "volume"): string | null {
  const text = value.trim();
  if (!text) return null;
  if (!/^\d+(\.\d+)?$/.test(text)) {
    return kind === "weight"
      ? "Enter a weight in kilograms, or leave it empty."
      : "Enter a volume in cubic metres, or leave it empty.";
  }
  return null;
}

export function overrideProblem(reason: string): string | null {
  return reason.trim().length >= 3 ? null : "An override needs a reason.";
}
