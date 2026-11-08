import { createContext, useContext, useMemo, type ReactNode } from "react";
import { createTheme, type AppTheme } from "./tokens";

const ThemeContext = createContext<AppTheme>(createTheme());

export function ThemeProvider({ primary, children }: { primary?: string | null; children: ReactNode }) {
  const theme = useMemo(() => createTheme(primary && /^#[0-9A-Fa-f]{6}$/.test(primary) ? primary : undefined), [primary]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): AppTheme {
  return useContext(ThemeContext);
}
