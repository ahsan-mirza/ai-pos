import { Permission, isSupportedCurrency, type BusinessSettings, type CurrencyCode } from "@ai-pos/shared-types";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { env } from "../config/env";
import { apiGet, apiPut } from "./api";
import { useAuth } from "./auth";
import { syncPrimaryColor } from "./theme";

interface CurrencyContextValue {
  currency: CurrencyCode;
  settings: BusinessSettings | null;
  loadError: string | null;
  saveCurrency: (currency: CurrencyCode) => Promise<BusinessSettings>;
  /** Shares a settings response from another endpoint (e.g. PUT /settings/tax) with the whole portal. */
  applySettings: (settings: BusinessSettings) => void;
}

const CurrencyContext = createContext<CurrencyContextValue | null>(null);
const fallback: CurrencyCode = isSupportedCurrency(env.defaultCurrency) ? env.defaultCurrency : "USD";
const CACHE_KEY = "ai-pos.business-settings";

function readCached(): BusinessSettings | null {
  try {
    const raw = localStorage.getItem(CACHE_KEY);
    if (raw === null) return null;
    const parsed = JSON.parse(raw) as BusinessSettings;
    return typeof parsed?.currency === "string" && isSupportedCurrency(parsed.currency) ? parsed : null;
  } catch {
    return null;
  }
}

function writeCached(settings: BusinessSettings): void {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(settings));
  } catch {
    // Storage full or disabled: the in-memory copy still serves this tab.
  }
}

/**
 * The business settings are owned by the API (stored in the database and cached server-side). The portal keeps
 * the last response in localStorage so pages render at once on reload, then revalidates against the API.
 */
export function CurrencyProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const [settings, setSettings] = useState<BusinessSettings | null>(() => readCached());
  const [loadError, setLoadError] = useState<string | null>(null);

  const applySettings = useCallback((next: BusinessSettings) => {
    syncPrimaryColor(next.primary_color ?? null);
    setSettings((current) => {
      if (
        current?.entitlement_revision !== undefined &&
        current.entitlement_revision === next.entitlement_revision &&
        current.updated_at === next.updated_at &&
        current.currency === next.currency &&
        current.trn === next.trn &&
        current.country === next.country
      ) {
        return current;
      }
      writeCached(next);
      return next;
    });
  }, []);

  useEffect(() => {
    if (status !== "signed-in") return;
    let cancelled = false;
    const load = () => {
      apiGet<BusinessSettings>("/api/v1/settings")
        .then((next) => {
          if (cancelled) return;
          applySettings(next);
          setLoadError(null);
        })
        .catch((error: unknown) => {
          if (!cancelled) setLoadError(error instanceof Error ? error.message : "Settings could not be loaded.");
        });
    };
    load();
    const timer = window.setInterval(load, 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [status, applySettings]);

  const saveCurrency = useCallback(
    async (currency: CurrencyCode) => {
      const next = await apiPut<BusinessSettings>("/api/v1/settings/currency", { currency });
      applySettings(next);
      return next;
    },
    [applySettings],
  );

  const value = useMemo<CurrencyContextValue>(
    () => ({ currency: settings?.currency ?? fallback, settings, loadError, saveCurrency, applySettings }),
    [settings, loadError, saveCurrency, applySettings],
  );
  return <CurrencyContext.Provider value={value}>{children}</CurrencyContext.Provider>;
}

/** Mirrors the API rule: only business-wide users holding settings:manage may change business settings. */
export function useCanManageSettings(): boolean {
  const { can, user } = useAuth();
  return can(Permission.SettingsManage) && user?.store_id === null;
}

export function useCurrency(): CurrencyContextValue {
  const value = useContext(CurrencyContext);
  if (value === null) {
    throw new Error("CurrencyProvider is missing.");
  }
  return value;
}
