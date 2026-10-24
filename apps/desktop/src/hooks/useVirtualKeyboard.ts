import { createContext, createElement, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { inTauri } from "../lib/tauri";

export type ConnectionType = "wired" | "bluetooth" | "surface_cover" | "none";
export type KeyboardLayout = "qwerty" | "numeric";

export interface KeyboardStatus {
  hasPhysicalKeyboard: boolean;
  connectionType: ConnectionType;
  isTouchDevice: boolean;
}

interface VirtualKeyboardApi {
  status: KeyboardStatus;
  /** True when the on-screen keyboard is allowed to open. */
  enabled: boolean;
  layout: KeyboardLayout | null;
  toggle: () => void;
  hide: () => void;
  press: (key: string) => void;
}

const ABSENT: KeyboardStatus = {
  hasPhysicalKeyboard: true,
  connectionType: "wired",
  isTouchDevice: false,
};

const KeyboardContext = createContext<VirtualKeyboardApi | null>(null);

function browserStatus(): KeyboardStatus {
  const fine = window.matchMedia("(pointer: fine)").matches;
  const touch = navigator.maxTouchPoints > 0 || window.matchMedia("(pointer: coarse)").matches;
  return {
    hasPhysicalKeyboard: fine,
    connectionType: fine ? "wired" : "none",
    isTouchDevice: touch,
  };
}

function isTextField(element: HTMLElement): element is HTMLInputElement | HTMLTextAreaElement {
  if (element instanceof HTMLTextAreaElement) return !element.disabled && !element.readOnly;
  if (!(element instanceof HTMLInputElement) || element.disabled || element.readOnly) return false;
  const blocked = ["button", "checkbox", "radio", "file", "range", "color", "date", "time", "datetime-local", "hidden", "submit", "reset"];
  return !blocked.includes(element.type);
}

/** QWERTY for names and notes, a numpad for money, PIN, and barcode digits, never for a scanner field. */
export function layoutFor(element: HTMLElement): KeyboardLayout | "disabled" {
  const mode = element.getAttribute("data-virtual-keyboard");
  if (mode === "disabled") return "disabled";
  if (mode === "numeric" || mode === "numpad") return "numeric";
  if (mode === "text" || mode === "qwerty") return "qwerty";
  if (element instanceof HTMLInputElement) {
    if (element.type === "password" || element.type === "number" || element.type === "tel") return "numeric";
    if (element.inputMode === "numeric" || element.inputMode === "decimal" || element.inputMode === "tel") return "numeric";
  }
  return "qwerty";
}

function writeField(element: HTMLInputElement | HTMLTextAreaElement, key: string) {
  const start = element.selectionStart ?? element.value.length;
  const end = element.selectionEnd ?? element.value.length;
  const next =
    key === "backspace"
      ? element.value.slice(0, start === end && start > 0 ? start - 1 : start) + element.value.slice(end)
      : key === "clear"
        ? ""
        : element.value.slice(0, start) + key + element.value.slice(end);
  const prototype = element instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(prototype, "value")?.set?.call(element, next);
  const cursor = key === "backspace" ? Math.max(0, (start === end ? start - 1 : start)) : key === "clear" ? 0 : start + key.length;
  element.setSelectionRange(cursor, cursor);
  element.dispatchEvent(new Event("input", { bubbles: true }));
}

export function VirtualKeyboardProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<KeyboardStatus>(ABSENT);
  const [override, setOverride] = useState<boolean | null>(null);
  const [target, setTarget] = useState<HTMLInputElement | HTMLTextAreaElement | null>(null);

  useEffect(() => {
    let stop = () => {};
    let cancelled = false;
    if (!inTauri()) {
      setStatus(browserStatus());
      return;
    }
    void (async () => {
      const { invoke } = await import("@tauri-apps/api/core");
      const { listen } = await import("@tauri-apps/api/event");
      if (cancelled) return;
      try {
        setStatus(await invoke<KeyboardStatus>("check_hardware_keyboard_status"));
      } catch {
        setStatus(browserStatus());
      }
      const unlisten = await listen<KeyboardStatus>("keyboard-hardware-change", (event) => setStatus(event.payload));
      if (cancelled) unlisten();
      else stop = unlisten;
    })();
    return () => {
      cancelled = true;
      stop();
    };
  }, []);

  useEffect(() => {
    const onFocus = (event: FocusEvent) => {
      const element = event.target;
      if (!(element instanceof HTMLElement) || element.closest("[data-virtual-keyboard-root]")) return;
      if (!isTextField(element) || layoutFor(element) === "disabled") {
        setTarget(null);
        return;
      }
      setTarget(element);
    };
    document.addEventListener("focusin", onFocus);
    return () => document.removeEventListener("focusin", onFocus);
  }, []);

  const autoEnabled = !status.hasPhysicalKeyboard && status.isTouchDevice;
  const enabled = override ?? autoEnabled;
  const field = target?.isConnected ? target : null;
  const requested = field && enabled ? layoutFor(field) : "disabled";
  const layout: KeyboardLayout | null = requested === "disabled" ? null : requested;

  useEffect(() => {
    if (layout && field) field.scrollIntoView({ block: "center" });
  }, [layout, field]);

  const toggle = useCallback(() => {
    setOverride((current) => (current === null ? !autoEnabled : null));
  }, [autoEnabled]);

  const hide = useCallback(() => {
    setOverride(autoEnabled ? false : null);
  }, [autoEnabled]);

  const press = useCallback(
    (key: string) => {
      const element = field;
      if (!element || !element.isConnected) return;
      element.focus();
      if (key === "enter") {
        element.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
        return;
      }
      writeField(element, key === "space" ? " " : key);
    },
    [field],
  );

  const api = useMemo<VirtualKeyboardApi>(
    () => ({ status, enabled, layout, toggle, hide, press }),
    [status, enabled, layout, toggle, hide, press],
  );

  return createElement(KeyboardContext.Provider, { value: api }, children);
}

export function useVirtualKeyboard(): VirtualKeyboardApi {
  const api = useContext(KeyboardContext);
  if (!api) throw new Error("useVirtualKeyboard must be used inside VirtualKeyboardProvider");
  return api;
}
