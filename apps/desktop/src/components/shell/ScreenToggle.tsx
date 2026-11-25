import { useLocale } from "@ai-pos/ui";
import { Maximize2, Minimize2 } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { isFullscreenShortcut, launchScreenMode, reduceScreenMode, screenControl, type ScreenMode } from "../../lib/fullscreen";
import { inTauri, readWindowFullscreen, toggleWindowFullscreen } from "../../lib/tauri";
import { drawerButtonClass } from "./settingsEntry";

interface ScreenModeValue {
  available: boolean;
  fullscreen: boolean;
  pending: boolean;
  toggle: () => void;
}

const ScreenModeContext = createContext<ScreenModeValue | null>(null);

export function ScreenModeProvider({ children }: { children: ReactNode }) {
  const value = useScreenModeState();
  return <ScreenModeContext.Provider value={value}>{children}</ScreenModeContext.Provider>;
}

function useScreenMode(): ScreenModeValue {
  const value = useContext(ScreenModeContext);
  if (value === null) throw new Error("ScreenModeProvider is missing.");
  return value;
}

function useScreenModeState(): ScreenModeValue {
  const available = inTauri();
  const [state, setState] = useState<ScreenMode>(launchScreenMode);
  const pending = useRef(false);

  const apply = useCallback((event: Parameters<typeof reduceScreenMode>[1]) => {
    setState((current) => reduceScreenMode(current, event));
  }, []);

  useEffect(() => {
    if (!available) return;
    let live = true;
    let unlisten: (() => void) | undefined;
    void readWindowFullscreen()
      .then((fullscreen) => {
        if (live) apply({ type: "reported", fullscreen });
      })
      .catch(() => {
        if (live) apply({ type: "read-failed" });
      });
    void import("@tauri-apps/api/event")
      .then(({ listen }) =>
        listen<boolean>("pos-fullscreen-changed", (event) => {
          if (typeof event.payload === "boolean") apply({ type: "reported", fullscreen: event.payload });
        }),
      )
      .then((stop) => {
        if (!live) stop();
        else unlisten = stop;
      })
      .catch(() => undefined);
    return () => {
      live = false;
      unlisten?.();
    };
  }, [apply, available]);

  const toggle = useCallback(() => {
    if (!available || pending.current) return;
    pending.current = true;
    apply({ type: "toggle-start" });
    void toggleWindowFullscreen()
      .then((fullscreen) => apply({ type: "toggle-done", fullscreen }))
      .catch(() => {
        void readWindowFullscreen()
          .then((fullscreen) => {
            apply({ type: "toggle-failed" });
            apply({ type: "reported", fullscreen });
          })
          .catch(() => apply({ type: "read-failed" }));
      })
      .finally(() => {
        pending.current = false;
      });
  }, [apply, available]);

  return { available, fullscreen: state.fullscreen, pending: state.pending, toggle };
}

/** F11 toggles the native window. Escape is left to dialogs and the sale screen. */
export function FullscreenHotkey() {
  const { toggle, available } = useScreenMode();
  useEffect(() => {
    if (!available) return;
    const onKey = (event: KeyboardEvent) => {
      if (!isFullscreenShortcut(event)) return;
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [available, toggle]);
  return null;
}

export function ScreenToggleButton({
  fullscreen,
  pending = false,
  onToggle,
}: {
  fullscreen: boolean;
  pending?: boolean;
  onToggle: () => void;
}) {
  const { t } = useLocale();
  const control = screenControl(fullscreen);
  const Icon = control.icon === "minimize" ? Minimize2 : Maximize2;
  const label = t(control.label);
  return (
    <button
      type="button"
      data-pos-screen-toggle=""
      data-screen-mode={fullscreen ? "full" : "window"}
      aria-pressed={fullscreen}
      aria-busy={pending}
      aria-keyshortcuts="F11"
      aria-label={label}
      title={label}
      onClick={onToggle}
      className={drawerButtonClass}
    >
      <Icon aria-hidden="true" className="h-4 w-4" />
    </button>
  );
}

/** One navbar icon. Hidden in a browser preview, where there is no native window. */
export function ScreenToggle() {
  const { available, fullscreen, pending, toggle } = useScreenMode();
  if (!available) return null;
  return <ScreenToggleButton fullscreen={fullscreen} pending={pending} onToggle={toggle} />;
}
