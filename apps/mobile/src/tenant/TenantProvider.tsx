import { isBusinessProfile, type BusinessSettings } from "@ai-pos/shared-types";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet } from "@/api/client";
import { useAuth } from "@/auth/AuthProvider";
import { ThemeProvider } from "@/theme/ThemeProvider";

interface TenantProfile {
  business_type: string;
  enabled_modules: string[];
}

interface TenantValue {
  ready: boolean;
  profile: string | null;
  capabilities: readonly string[];
  capabilitiesKnown: boolean;
  currency: string;
  businessName: string | null;
  /** Tenant slug. This is the store code typed to sign in and to activate a register. */
  storeCode: string | null;
  primaryColor: string | null;
  storeId: string | null;
}

const TenantContext = createContext<TenantValue | null>(null);

export function TenantProvider({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const [settings, setSettings] = useState<BusinessSettings | null>(null);
  const [profile, setProfile] = useState<TenantProfile | null>(null);

  useEffect(() => {
    if (status !== "signed-in") {
      setSettings(null);
      setProfile(null);
      return;
    }
    let cancelled = false;
    void Promise.all([
      apiGet<BusinessSettings>("/api/v1/settings").catch(() => null),
      apiGet<TenantProfile>("/api/v1/tenant/profile").catch(() => null),
    ]).then(([nextSettings, nextProfile]) => {
      if (cancelled) return;
      setSettings(nextSettings);
      setProfile(nextProfile);
    });
    return () => {
      cancelled = true;
    };
  }, [status, user?.id]);

  const value = useMemo<TenantValue>(() => {
    const stored = settings?.business_profile ?? profile?.business_type ?? null;
    const capabilities = settings?.capabilities ?? profile?.enabled_modules ?? [];
    return {
      ready: settings !== null || profile !== null,
      profile: stored !== null && isBusinessProfile(stored) ? stored : stored,
      capabilities,
      capabilitiesKnown: settings !== null || profile !== null,
      currency: settings?.currency ?? "AED",
      businessName: settings?.legal_name ?? null,
      storeCode: settings?.store_code?.trim() ? settings.store_code.trim() : null,
      primaryColor: settings?.primary_color ?? null,
      storeId: user?.store_id ?? null,
    };
  }, [settings, profile, user?.store_id]);

  return (
    <TenantContext.Provider value={value}>
      <ThemeProvider primary={value.primaryColor}>{children}</ThemeProvider>
    </TenantContext.Provider>
  );
}

export function useTenant(): TenantValue {
  const value = useContext(TenantContext);
  if (value === null) throw new Error("useTenant must be used inside TenantProvider.");
  return value;
}
