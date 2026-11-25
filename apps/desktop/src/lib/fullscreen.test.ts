import { describe, expect, it } from "vitest";
import {
  isFullscreenShortcut,
  launchScreenMode,
  reduceScreenMode,
  screenControl,
  type ScreenMode,
} from "./fullscreen";

const plain = { repeat: false, ctrlKey: false, altKey: false, metaKey: false, shiftKey: false };

describe("register full screen", () => {
  it("starts full screen on every launch", () => {
    expect(launchScreenMode()).toEqual({ fullscreen: true, pending: false });
  });

  it("returns to full screen on the next launch after a windowed session", () => {
    const windowed: ScreenMode = { fullscreen: false, pending: false };
    expect(windowed.fullscreen).toBe(false);
    expect(launchScreenMode().fullscreen).toBe(true);
  });

  it("shows the exit icon while full screen and the enter icon while windowed", () => {
    expect(screenControl(true)).toEqual({
      icon: "minimize",
      label: "Exit Full Screen",
      tooltip: "Exit Full Screen",
    });
    expect(screenControl(false)).toEqual({
      icon: "maximize",
      label: "Enter Full Screen",
      tooltip: "Enter Full Screen",
    });
  });

  it("follows the native state and toggles in both directions", () => {
    let state = reduceScreenMode(launchScreenMode(), { type: "reported", fullscreen: true });
    expect(screenControl(state.fullscreen).icon).toBe("minimize");
    state = reduceScreenMode(state, { type: "toggle-start" });
    state = reduceScreenMode(state, { type: "toggle-done", fullscreen: false });
    expect(state).toEqual({ fullscreen: false, pending: false });
    expect(screenControl(state.fullscreen).icon).toBe("maximize");
    state = reduceScreenMode(state, { type: "toggle-start" });
    state = reduceScreenMode(state, { type: "toggle-done", fullscreen: true });
    expect(state.fullscreen).toBe(true);
    state = reduceScreenMode(state, { type: "reported", fullscreen: false });
    expect(state.fullscreen).toBe(false);
  });

  it("ignores a second toggle and a resize report while a change is in progress", () => {
    const started = reduceScreenMode(launchScreenMode(), { type: "toggle-start" });
    expect(reduceScreenMode(started, { type: "toggle-start" })).toEqual(started);
    expect(reduceScreenMode(started, { type: "reported", fullscreen: false })).toEqual(started);
  });

  it("keeps a usable window when the native command fails", () => {
    const pending = reduceScreenMode(launchScreenMode(), { type: "toggle-start" });
    const failed = reduceScreenMode(pending, { type: "read-failed" });
    expect(failed).toEqual({ fullscreen: false, pending: false });
    expect(screenControl(failed.fullscreen).label).toBe("Enter Full Screen");
  });

  it("toggles on F11 and leaves Escape to the rest of the register", () => {
    expect(isFullscreenShortcut({ key: "F11", ...plain })).toBe(true);
    expect(isFullscreenShortcut({ key: "F11", ...plain, repeat: true })).toBe(false);
    expect(isFullscreenShortcut({ key: "F11", ...plain, ctrlKey: true })).toBe(false);
    expect(isFullscreenShortcut({ key: "F11", ...plain, altKey: true })).toBe(false);
    expect(isFullscreenShortcut({ key: "F11", ...plain, metaKey: true })).toBe(false);
    expect(isFullscreenShortcut({ key: "F11", ...plain, shiftKey: true })).toBe(false);
    expect(isFullscreenShortcut({ key: "Escape", ...plain })).toBe(false);
  });
});
