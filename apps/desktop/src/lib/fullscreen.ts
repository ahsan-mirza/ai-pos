/** Session screen mode for the register window. A new launch always starts full-screen. */

export interface ScreenMode {
  fullscreen: boolean;
  pending: boolean;
}

export type ScreenEvent =
  | { type: "reported"; fullscreen: boolean }
  | { type: "toggle-start" }
  | { type: "toggle-done"; fullscreen: boolean }
  | { type: "toggle-failed" }
  | { type: "read-failed" };

export interface ScreenControl {
  icon: "minimize" | "maximize";
  label: "Exit Full Screen" | "Enter Full Screen";
  tooltip: "Exit Full Screen" | "Enter Full Screen";
}

export interface ShortcutKey {
  key: string;
  repeat: boolean;
  ctrlKey: boolean;
  altKey: boolean;
  metaKey: boolean;
  shiftKey: boolean;
}

export function launchScreenMode(): ScreenMode {
  return { fullscreen: true, pending: false };
}

export function reduceScreenMode(state: ScreenMode, event: ScreenEvent): ScreenMode {
  switch (event.type) {
    case "reported":
      if (state.pending) return state;
      return { ...state, fullscreen: event.fullscreen };
    case "toggle-start":
      if (state.pending) return state;
      return { ...state, pending: true };
    case "toggle-done":
      return { fullscreen: event.fullscreen, pending: false };
    case "toggle-failed":
      return { ...state, pending: false };
    case "read-failed":
      return { fullscreen: false, pending: false };
  }
}

/** Full-screen shows the exit icon. Windowed shows the enter icon. One control, two states. */
export function screenControl(fullscreen: boolean): ScreenControl {
  if (fullscreen) {
    return { icon: "minimize", label: "Exit Full Screen", tooltip: "Exit Full Screen" };
  }
  return { icon: "maximize", label: "Enter Full Screen", tooltip: "Enter Full Screen" };
}

/** F11 toggles native full-screen. Escape is never used for that. */
export function isFullscreenShortcut(event: ShortcutKey): boolean {
  return event.key === "F11" && !event.repeat && !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey;
}
