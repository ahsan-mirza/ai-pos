import type { RegisterView } from "../../components/shell/ShellContext";
import { laundryStationFromLocation } from "./laundryRoute";
import { visibleStations, type Station } from "./productionAccess";

export type LaundrySection = "orders" | "production" | "services" | "customers" | "reports" | "settings";

export interface LaundryTab {
  id: string;
  label: string;
}

const ORDER_TABS: LaundryTab[] = [
  { id: "intake", label: "New Order" },
  { id: "active", label: "Active Orders" },
  { id: "lookup", label: "Order Lookup" },
  { id: "ready", label: "Ready for Collection" },
];

/** Floor stations that stay under Production. Ready for Collection stays with Orders. */
const PRODUCTION_ORDER = ["scan", "sorting", "production", "machines", "quality", "rework", "packing", "incidents", "shift"] as const;

const SERVICE_TABS: LaundryTab[] = [
  { id: "services", label: "Laundry Services" },
  { id: "categories", label: "Service Categories" },
  { id: "garment-types", label: "Garment Types" },
  { id: "pricing", label: "Service Pricing" },
];

const EXTRA: Station[] = [
  { id: "active", label: "Active Orders", group: "operations" },
  { id: "services", label: "Laundry Services", group: "management" },
  { id: "categories", label: "Service Categories", group: "management" },
  { id: "garment-types", label: "Garment Types", group: "management" },
  { id: "pricing", label: "Service Pricing", group: "management" },
  { id: "customers", label: "Customers", group: "operations" },
];

/** Existing floor stations plus the read-only catalogue and order list. No new order store. */
export function workspaceDestinations(permissions: readonly string[]): Station[] {
  const stations = visibleStations(permissions);
  if (stations.length === 0) return [];
  return [...stations, ...EXTRA];
}

export function primaryTabs(): LaundryTab[] {
  return [
    { id: "orders", label: "Orders" },
    { id: "production", label: "Production" },
    { id: "services", label: "Services" },
    { id: "customers", label: "Customers" },
    { id: "reports", label: "Reports" },
  ];
}

export function sectionOf(station: string): LaundrySection {
  if (station === "intake" || station === "active" || station === "lookup" || station === "ready" || station === "dashboard") return "orders";
  if (station === "customers") return "customers";
  if (station === "services" || station === "categories" || station === "garment-types" || station === "pricing") return "services";
  if (station === "settings") return "settings";
  if (station === "shift") return "reports";
  return "production";
}

export function secondaryTabs(section: LaundrySection, stations: readonly Station[]): LaundryTab[] {
  const ids = new Set(stations.map((station) => station.id));
  if (section === "orders") return ORDER_TABS.filter((tab) => tab.id === "active" || ids.has(tab.id));
  if (section === "production") {
    return PRODUCTION_ORDER.filter((id) => ids.has(id)).map((id) => ({
      id,
      label: stations.find((station) => station.id === id)?.label ?? id,
    }));
  }
  if (section === "services") return SERVICE_TABS;
  if (section === "customers") return [{ id: "customers", label: "Customers" }];
  if (section === "reports") return [{ id: "shift", label: "Shift Summary" }];
  return [];
}

export function defaultStation(section: LaundrySection, stations: readonly Station[]): string {
  const tabs = secondaryTabs(section, stations);
  if (section === "orders" && tabs.some((tab) => tab.id === "intake")) return "intake";
  return tabs[0]?.id ?? stations[0]?.id ?? "dashboard";
}

/** Empty and bare laundry hashes open New Order. An explicit station, including the dashboard, is kept. */
export function openingStation(hash: string, allowed: readonly string[]): string {
  const requested = laundryStationFromLocation(hash);
  const explicitDashboard = /\/laundry\/dashboard(?:$|[?#])/.test(hash);
  if (requested !== null && allowed.includes(requested) && (requested !== "dashboard" || explicitDashboard)) return requested;
  if (allowed.includes("intake")) return "intake";
  return allowed[0] ?? "dashboard";
}

/** Laundry businesses take orders. Retail businesses keep Checkout. */
export function registerPageLabel(profile: string, pageId: string, label: string): string {
  return profile === "laundry" && pageId === "checkout" ? "Orders" : label;
}

export function registerPageTarget(profile: string, pageId: RegisterView): RegisterView {
  return profile === "laundry" && pageId === "checkout" ? "laundry" : pageId;
}
