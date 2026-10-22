import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type RegisterTheme = "light" | "dark";

interface RegisterLayoutValue {
  railCollapsed: boolean;
  toggleRail: () => void;
  theme: RegisterTheme;
  setTheme: (theme: RegisterTheme) => void;
}

const RAIL_KEY = "ai-pos.register.rail-collapsed";
const THEME_KEY = "ai-pos.register.theme";

const RegisterLayoutContext = createContext<RegisterLayoutValue | null>(null);

function stored<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = window.localStorage.getItem(key);
    return allowed.includes(value as T) ? (value as T) : fallback;
  } catch {
    return fallback;
  }
}

/** Register-wide layout preferences (sidebar width, colour theme), remembered per device. Dark by default. */
export function RegisterLayoutProvider({ children }: { children: ReactNode }) {
  const [railCollapsed, setRailCollapsed] = useState(() => stored(RAIL_KEY, ["1", "0"], "0") === "1");
  const [theme, setTheme] = useState<RegisterTheme>(() => stored(THEME_KEY, ["light", "dark"], "dark"));

  useEffect(() => {
    try {
      window.localStorage.setItem(RAIL_KEY, railCollapsed ? "1" : "0");
      window.localStorage.setItem(THEME_KEY, theme);
    } catch {
      // Storage can be unavailable (private mode); preferences then last for the session only.
    }
  }, [railCollapsed, theme]);

  const toggleRail = useCallback(() => setRailCollapsed((value) => !value), []);
  const value = useMemo(() => ({ railCollapsed, toggleRail, theme, setTheme }), [railCollapsed, toggleRail, theme]);
  return <RegisterLayoutContext.Provider value={value}>{children}</RegisterLayoutContext.Provider>;
}

export function useRegisterLayout(): RegisterLayoutValue {
  const value = useContext(RegisterLayoutContext);
  if (value === null) throw new Error("RegisterLayoutProvider is missing.");
  return value;
}
