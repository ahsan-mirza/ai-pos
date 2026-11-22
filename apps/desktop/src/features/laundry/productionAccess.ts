import { Permission } from "@ai-pos/shared-types";

export type StationGroup = "operations" | "production" | "management";

export interface Station {
  id: string;
  label: string;
  group: StationGroup;
}

export const stationGroupLabels: Record<StationGroup, string> = {
  operations: "Daily operations",
  production: "Production",
  management: "Management",
};

export const OFFLINE_PRODUCTION =
  "Production needs the server. Machine, batch, and stage changes stay disabled until the register is online.";

function has(permissions: readonly string[], ...keys: string[]): boolean {
  return keys.some((key) => permissions.includes(key));
}

/** Stations the signed-in user is allowed to open. An empty list hides the laundry workspace. */
export function visibleStations(permissions: readonly string[]): Station[] {
  const view = has(
    permissions,
    Permission.LaundryProductionView,
    Permission.LaundryOrdersView,
    Permission.LaundryOrdersCreate,
    Permission.LaundryGarmentsView,
    Permission.LaundryProductionSort,
    Permission.LaundryProductionProcess,
    Permission.LaundryProductionFinish,
    Permission.LaundryQualityInspect,
    Permission.LaundryPacking,
    Permission.LaundryIncidentsReport,
    Permission.LaundryIncidentsResolve,
    Permission.LaundryMachinesOperate,
    Permission.LaundryBatchesManage,
    Permission.LaundryProductionOverride,
  );
  if (!view) return [];
  const stations: Station[] = [{ id: "dashboard", label: "Dashboard", group: "operations" }];
  if (has(permissions, Permission.LaundryOrdersCreate)) stations.push({ id: "intake", label: "Order Intake", group: "operations" });
  stations.push({ id: "lookup", label: "Order Lookup", group: "operations" });
  stations.push({ id: "scan", label: "Scan Garment", group: "operations" });
  if (has(permissions, Permission.LaundryProductionSort, Permission.LaundryProductionOverride)) {
    stations.push({ id: "sorting", label: "Sorting", group: "production" });
  }
  if (
    has(
      permissions,
      Permission.LaundryProductionProcess,
      Permission.LaundryProductionFinish,
      Permission.LaundryProductionOverride,
    )
  ) {
    stations.push({ id: "production", label: "Production", group: "production" });
  }
  if (has(permissions, Permission.LaundryMachinesOperate, Permission.LaundryBatchesManage)) {
    stations.push({ id: "machines", label: "Machines", group: "production" });
  }
  if (has(permissions, Permission.LaundryQualityInspect)) stations.push({ id: "quality", label: "Quality Control", group: "production" });
  if (has(permissions, Permission.LaundryQualityInspect, Permission.LaundryProductionProcess)) {
    stations.push({ id: "rework", label: "Rework", group: "production" });
  }
  if (has(permissions, Permission.LaundryPacking)) {
    stations.push({ id: "packing", label: "Packing", group: "production" }, { id: "ready", label: "Ready Orders", group: "production" });
  }
  if (has(permissions, Permission.LaundryIncidentsReport, Permission.LaundryIncidentsResolve)) {
    stations.push({ id: "incidents", label: "Incidents", group: "management" });
  }
  stations.push({ id: "shift", label: "Shift Summary", group: "management" });
  stations.push({ id: "settings", label: "Laundry Settings", group: "management" });
  return stations;
}
