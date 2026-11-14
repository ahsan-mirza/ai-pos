import { Moon, Sun } from "lucide-react";
import { useEffect, useSyncExternalStore } from "react";
import { useLocale } from "./LocaleSwitch";

export type ThemeChoice = "light" | "dark";

const KEY = "ai-pos.theme";
const listeners = new Set<() => void>();

function prefersDark(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function storedChoice(): ThemeChoice {
  try {
    const value = globalThis.localStorage?.getItem(KEY);
    if (value === "light" || value === "dark") return value;
    if (value === "system") {
      const next = prefersDark() ? "dark" : "light";
      globalThis.localStorage?.setItem(KEY, next);
      return next;
    }
  } catch {
    /* Storage can be blocked. The portal stays light. */
  }
  return "light";
}

let memory: ThemeChoice = storedChoice();

export function applyTheme(choice: ThemeChoice = memory): void {
  if (typeof document === "undefined") return;
  const dark = choice === "dark";
  document.documentElement.classList.toggle("dark", dark);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

export function readTheme(): ThemeChoice {
  return memory;
}

export function setTheme(choice: ThemeChoice): void {
  memory = choice;
  try {
    globalThis.localStorage?.setItem(KEY, choice);
  } catch {
    /* The current page still switches. */
  }
  applyTheme(choice);
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Light or dark. The choice is stored on this browser, like the language. */
export function ThemeSwitch({ className = "" }: { className?: string }) {
  const { t } = useLocale();
  const choice = useSyncExternalStore(subscribe, readTheme, (): ThemeChoice => "light");

  useEffect(() => {
    applyTheme(choice);
  }, [choice]);

  const item = (id: ThemeChoice, label: string, icon: typeof Sun) => {
    const Icon = icon;
    const selected = choice === id;
    return (
      <button
        type="button"
        aria-pressed={selected}
        aria-label={label}
        title={label}
        onClick={() => setTheme(id)}
        className={`inline-flex h-8 w-8 items-center justify-center rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-500/50 ${
          selected ? "bg-zinc-100 text-charcoal shadow-sm dark:bg-zinc-600 dark:text-white" : "text-charcoal/60 dark:text-zinc-400"
        }`}
      >
        <Icon size={14} aria-hidden="true" />
      </button>
    );
  };

  return (
    <div
      role="group"
      aria-label={t("Theme")}
      className={`inline-flex items-center gap-0.5 rounded-full bg-charcoal/[0.04] p-0.5 dark:bg-zinc-800 ${className}`}
    >
      {item("light", t("Use the light theme"), Sun)}
      {item("dark", t("Use the dark theme"), Moon)}
    </div>
  );
}
