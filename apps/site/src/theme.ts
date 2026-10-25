import { useEffect, useState } from "react";

const KEY = "axizpos.site-theme";
export type SiteTheme = "light" | "dark";

function readTheme(): SiteTheme {
  try {
    return localStorage.getItem(KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

/** Light matches the admin portal. Dark keeps the same orange, type, and surfaces. */
export function useSiteTheme(): { theme: SiteTheme; toggle: () => void } {
  const [theme, setTheme] = useState<SiteTheme>("light");

  useEffect(() => {
    setTheme(readTheme());
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
  }, [theme]);

  function toggle() {
    const next: SiteTheme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    try {
      localStorage.setItem(KEY, next);
    } catch {
      // The class still applies for this visit.
    }
  }

  return { theme, toggle };
}
