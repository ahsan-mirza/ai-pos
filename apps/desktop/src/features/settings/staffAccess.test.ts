import { describe, expect, it } from "vitest";
import { canManageStaff, pinIsAcceptable, rolesActorMayGrant, seatLabel, staffStatus, type StaffRow } from "./staffAccess";

const row = (patch: Partial<StaffRow>): StaffRow => ({
  name: "Nora",
  username: "nora",
  role: "Cashier",
  branch: "Downtown",
  provisioning: "pending",
  active: true,
  ...patch,
});

describe("staff access", () => {
  it("shows a local cashier as pending rather than globally active", () => {
    expect(staffStatus(row({}))).toBe("LOCAL ACTIVE · PENDING SERVER PROVISIONING");
    expect(staffStatus(row({ provisioning: "server" }))).toBe("SERVER ACTIVE");
    expect(staffStatus(row({ provisioning: "rejected", active: false }))).toBe("PROVISIONING REJECTED");
    expect(staffStatus(row({ provisioning: "pending", active: false }))).toBe("DISABLED LOCALLY");
  });

  it("lets a store manager manage staff and refuses a cashier and platform admin", () => {
    expect(canManageStaff("Store Manager", ["users:create", "pos:access"])).toBe(true);
    expect(canManageStaff("Super Admin", ["users:create"])).toBe(true);
    expect(canManageStaff("Cashier", ["pos:access"])).toBe(false);
    expect(canManageStaff("Platform Super Admin", ["users:create"])).toBe(false);
    expect(seatLabel(2, 5)).toBe("2 / 5");
    expect(rolesActorMayGrant("Store Manager")).toEqual(["Cashier"]);
    expect(rolesActorMayGrant("Super Admin")).toEqual(["Cashier", "Store Manager"]);
    expect(rolesActorMayGrant("Cashier")).toEqual([]);
    expect(pinIsAcceptable("1357")).toBe(true);
    expect(pinIsAcceptable("12")).toBe(false);
  });
});
