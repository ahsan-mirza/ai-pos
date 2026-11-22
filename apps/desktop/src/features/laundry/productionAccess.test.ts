import { Permission } from "@ai-pos/shared-types";
import { describe, expect, it } from "vitest";
import { OFFLINE_PRODUCTION, visibleStations } from "./productionAccess";

describe("laundry production access", () => {
  it("hides the floor from a cashier with no laundry permissions", () => {
    expect(visibleStations([Permission.PosAccess])).toEqual([]);
  });

  it("shows sorting to a sorter and keeps machine controls off that role", () => {
    const stations = visibleStations([Permission.LaundryProductionSort, Permission.PortalAccess]).map((station) => station.id);
    expect(stations).toContain("sorting");
    expect(stations).toContain("scan");
    expect(stations).not.toContain("machines");
    expect(stations).not.toContain("intake");
  });

  it("keeps intake on the order permission and tells the operator production is offline", () => {
    const stations = visibleStations([Permission.LaundryOrdersCreate]).map((station) => station.id);
    expect(stations).toContain("intake");
    expect(stations).not.toContain("quality");
    expect(OFFLINE_PRODUCTION).toMatch(/needs the server/i);
  });
});
