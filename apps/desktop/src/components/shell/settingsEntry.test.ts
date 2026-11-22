import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  drawerButtonClass,
  isSettingsHash,
  openSettings,
  openSidebarPage,
  ordersRailActive,
  settingsGearActive,
} from "./settingsEntry";

function installWindow(hash = ""): void {
  const location = { pathname: "/", search: "", hash };
  class HashChangeEvent {
    constructor(public type: string) {}
  }
  const fake = {
    location,
    history: {
      pushState(_data: unknown, _title: string, url: string) {
        const hashAt = url.indexOf("#");
        location.hash = hashAt >= 0 ? url.slice(hashAt) : "";
      },
      replaceState(_data: unknown, _title: string, url: string) {
        const hashAt = url.indexOf("#");
        location.hash = hashAt >= 0 ? url.slice(hashAt) : "";
      },
    },
    dispatchEvent() {
      return true;
    },
    HashChangeEvent,
  };
  Object.assign(globalThis, { window: fake, HashChangeEvent });
}

beforeEach(() => installWindow());
afterEach(() => installWindow());

describe("shared settings entry", () => {
  it("keeps one drawer control class for the navbar", () => {
    expect(drawerButtonClass).toContain("h-10");
    expect(drawerButtonClass).toContain("w-10");
    expect(drawerButtonClass).toContain("rounded-full");
    expect(drawerButtonClass).toContain("disabled:opacity-40");
  });

  it("opens the shared store settings page for every profile", () => {
    const navigate = vi.fn();
    openSettings("laundry", navigate);
    expect(window.location.hash).toBe("#/settings");
    expect(isSettingsHash(window.location.hash)).toBe(true);
    expect(isSettingsHash("#/laundry/settings")).toBe(false);
    expect(navigate).toHaveBeenCalledWith("settings");

    navigate.mockClear();
    openSettings("retail_grocery", navigate);
    expect(navigate).toHaveBeenCalledWith("settings");
  });

  it("marks the sidebar gear active on the shared settings route", () => {
    expect(settingsGearActive("laundry", "settings", "#/settings/currency")).toBe(true);
    expect(settingsGearActive("laundry", "laundry", "#/laundry/settings")).toBe(false);
    expect(settingsGearActive("laundry", "laundry", "#/laundry/intake")).toBe(false);
    expect(ordersRailActive("laundry", "laundry", "#/laundry/intake")).toBe(true);
    expect(ordersRailActive("laundry", "laundry", "#/laundry/settings")).toBe(false);
    expect(settingsGearActive("restaurant", "settings", "")).toBe(true);
    expect(settingsGearActive("retail_fashion", "checkout", "")).toBe(false);
    expect(ordersRailActive("electronics", "checkout", "")).toBe(true);
  });

  it("leaves laundry settings for New Order and drops the shared settings hash", () => {
    const navigate = vi.fn();
    window.history.replaceState(null, "", "/#/laundry/settings");
    openSidebarPage("laundry", "checkout", navigate);
    expect(window.location.hash).toBe("#/laundry/intake");
    expect(navigate).toHaveBeenCalledWith("laundry");

    navigate.mockClear();
    window.history.replaceState(null, "", "/#/settings");
    openSidebarPage("cafe", "checkout", navigate);
    expect(window.location.hash).toBe("");
    expect(navigate).toHaveBeenCalledWith("checkout");
  });
});