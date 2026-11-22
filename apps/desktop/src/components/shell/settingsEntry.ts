import { laundryLocation, laundryStationFromLocation } from "../../features/laundry/laundryRoute";
import type { RegisterView } from "./ShellContext";

/** Icon-only cash-drawer control in the top navbar. Pages do not restyle it. */
export const drawerButtonClass =
  "inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-zinc-200 bg-white text-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:opacity-40 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

function writeLaundryStation(station: string): void {
  const base = `${window.location.pathname}${window.location.search}`;
  window.history.pushState({ posView: "laundry", station }, "", `${base}${laundryLocation(station)}`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Shared settings route. `#/laundry/settings` is the laundry floor panel, not this page. */
export function isSettingsHash(hash: string): boolean {
  return hash === "#/settings" || hash.startsWith("#/settings/") || hash.startsWith("#/settings?");
}

function writeSettingsHash(): void {
  const base = `${window.location.pathname}${window.location.search}`;
  window.history.pushState({ posView: "settings", section: "overview" }, "", `${base}#/settings`);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

function clearSettingsHash(): void {
  if (!isSettingsHash(window.location.hash)) return;
  const base = `${window.location.pathname}${window.location.search}`;
  window.history.pushState({ posView: "register" }, "", base);
  window.dispatchEvent(new HashChangeEvent("hashchange"));
}

/** Sidebar gear. Every profile, including laundry, opens the shared store settings page. */
export function openSettings(profile: string, navigate: (view: RegisterView) => void): void {
  void profile;
  writeSettingsHash();
  navigate("settings");
}

/** Leaving laundry settings from the Orders sidebar entry returns to New Order. Other stations stay put. */
export function openSidebarPage(profile: string, pageId: RegisterView, navigate: (view: RegisterView) => void): void {
  const target = profile === "laundry" && pageId === "checkout" ? "laundry" : pageId;
  if (profile === "laundry" && target === "laundry" && laundryStationFromLocation(window.location.hash) === "settings") {
    writeLaundryStation("intake");
  }
  if (target !== "settings") clearSettingsHash();
  navigate(target);
}

export function settingsGearActive(profile: string, view: RegisterView, hash: string): boolean {
  void profile;
  return view === "settings" || isSettingsHash(hash);
}

export function ordersRailActive(profile: string, view: RegisterView, hash: string): boolean {
  if (profile !== "laundry") return view === "checkout";
  return (view === "laundry" || view === "checkout") && laundryStationFromLocation(hash) !== "settings";
}
