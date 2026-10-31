import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

export type RegisterTheme = "light" | "dark";
export type CatalogDensity = "compact" | "comfortable" | "large";

/** Cart stays a full-height sheet below this width so 1024×768 terminals are not split into two narrow columns. */
export const POS_DOCKED_MIN_PX = 1280;
export const POS_DOCKED_QUERY = `(min-width: ${POS_DOCKED_MIN_PX}px)`;

interface RegisterLayoutValue {
  railCollapsed: boolean;
  toggleRail: () => void;
  theme: RegisterTheme;
  setTheme: (theme: RegisterTheme) => void;
  density: CatalogDensity;
  setDensity: (density: CatalogDensity) => void;
  showImages: boolean;
  setShowImages: (show: boolean) => void;
}

const RAIL_KEY = "ai-pos.register.rail-collapsed";
const THEME_KEY = "ai-pos.register.theme";
const DENSITY_KEY = "ai-pos.register.density";
const IMAGES_KEY = "ai-pos.register.show-images";

const RegisterLayoutContext = createContext<RegisterLayoutValue | null>(null);

function readKey(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function writeKey(key: string, value: string) {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Storage can be unavailable; the choice then lasts for this session only.
  }
}

/** Light unless this device already saved light or dark. An unset key is not treated as a choice. */
export function resolveTheme(storedValue: string | null): RegisterTheme {
  return storedValue === "light" || storedValue === "dark" ? storedValue : "light";
}

export function resolveDensity(storedValue: string | null): CatalogDensity {
  return storedValue === "compact" || storedValue === "comfortable" || storedValue === "large" ? storedValue : "comfortable";
}

/** Column count follows the cashier's density. Cards in a row stretch to one height. */
export function catalogGridClass(density: CatalogDensity): string {
  const stretch = "grid items-stretch [&>li]:min-w-0 [&>li]:h-full";
  if (density === "compact") return `${stretch} grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6`;
  if (density === "large") return `${stretch} grid-cols-1 gap-4 min-[640px]:grid-cols-2 xl:grid-cols-3`;
  return `${stretch} grid-cols-1 gap-3 min-[420px]:grid-cols-2 md:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5`;
}

/** Register-wide layout preferences, remembered per device. Light and a comfortable catalog are the defaults. */
export function RegisterLayoutProvider({ children }: { children: ReactNode }) {
  const [railCollapsed, setRailCollapsed] = useState(() => {
    const saved = readKey(RAIL_KEY);
    if (saved === "1" || saved === "0") return saved === "1";
    return typeof window !== "undefined" && window.innerWidth < POS_DOCKED_MIN_PX;
  });
  const [theme, setThemeState] = useState<RegisterTheme>(() => resolveTheme(readKey(THEME_KEY)));
  const [density, setDensityState] = useState<CatalogDensity>(() => resolveDensity(readKey(DENSITY_KEY)));
  const [showImages, setShowImagesState] = useState(() => readKey(IMAGES_KEY) !== "0");

  const toggleRail = useCallback(() => {
    setRailCollapsed((value) => {
      const next = !value;
      writeKey(RAIL_KEY, next ? "1" : "0");
      return next;
    });
  }, []);
  const setTheme = useCallback((next: RegisterTheme) => {
    setThemeState(next);
    writeKey(THEME_KEY, next);
  }, []);
  const setDensity = useCallback((next: CatalogDensity) => {
    setDensityState(next);
    writeKey(DENSITY_KEY, next);
  }, []);
  const setShowImages = useCallback((next: boolean) => {
    setShowImagesState(next);
    writeKey(IMAGES_KEY, next ? "1" : "0");
  }, []);
  const value = useMemo(
    () => ({ railCollapsed, toggleRail, theme, setTheme, density, setDensity, showImages, setShowImages }),
    [railCollapsed, toggleRail, theme, setTheme, density, setDensity, showImages, setShowImages],
  );
  return <RegisterLayoutContext.Provider value={value}>{children}</RegisterLayoutContext.Provider>;
}

export function useRegisterLayout(): RegisterLayoutValue {
  const value = useContext(RegisterLayoutContext);
  if (value === null) throw new Error("RegisterLayoutProvider is missing.");
  return value;
}
