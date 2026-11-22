export const LOCAL_PENDING = "LOCAL ACTIVE · PENDING SERVER PROVISIONING";

export interface StaffRow {
  name: string;
  username: string;
  role: string;
  branch: string;
  provisioning: "server" | "pending" | "accepted" | "rejected";
  active: boolean;
}

export function staffStatus(row: StaffRow): string {
  if (!row.active && row.provisioning === "rejected") return "PROVISIONING REJECTED";
  if (!row.active && row.provisioning === "pending") return "DISABLED LOCALLY";
  if (!row.active) return "DISABLED SERVER";
  if (row.provisioning === "pending") return LOCAL_PENDING;
  if (row.provisioning === "rejected") return "PROVISIONING REJECTED";
  if (row.provisioning === "accepted" || row.provisioning === "server") return "SERVER ACTIVE";
  return "AWAITING SERVER UPDATE";
}

export function canManageStaff(role: string, permissions: string[]): boolean {
  if (role === "Cashier" || role === "Platform Super Admin") return false;
  return permissions.includes("users:create") && (role === "Store Manager" || role === "Super Admin");
}

export function seatLabel(active: number, limit: number | null): string {
  if (limit == null) return `${active} active staff`;
  return `${active} / ${limit}`;
}

export function rolesActorMayGrant(role: string): string[] {
  if (role === "Super Admin") return ["Cashier", "Store Manager"];
  if (role === "Store Manager") return ["Cashier"];
  return [];
}

export function pinIsAcceptable(pin: string): boolean {
  return pin.length === 4 && [...pin].every((item) => item >= "0" && item <= "9");
}
