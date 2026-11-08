import AsyncStorage from "@react-native-async-storage/async-storage";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { createTheme, type AppTheme } from "./tokens";

const THEME_KEY = "axizpos.theme";
export type ThemeMode = "light" | "dark";

type ThemeValue = AppTheme & { mode: ThemeMode; setMode: (mode: ThemeMode) => void };

const ThemeContext = createContext<ThemeValue>({ ...createTheme(), mode: "light", setMode: () => undefined });

export function ThemeProvider({ primary, children }: { primary?: string | null; children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("light");
  useEffect(() => {
    void AsyncStorage.getItem(THEME_KEY).then((stored) => {
      if (stored === "dark" || stored === "light") setModeState(stored);
    });
  }, []);
  const setMode = useCallback((next: ThemeMode) => {
    setModeState(next);
    void AsyncStorage.setItem(THEME_KEY, next);
  }, []);
  const theme = useMemo(() => {
    const color = primary && /^#[0-9A-Fa-f]{6}$/.test(primary) ? primary : undefined;
    return { ...createTheme(color, mode), mode, setMode };
  }, [mode, primary, setMode]);
  return <ThemeContext.Provider value={theme}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  return useContext(ThemeContext);
}
