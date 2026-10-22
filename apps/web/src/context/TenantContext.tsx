import { type BusinessProfile } from "@ai-pos/shared-types";
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { apiGet } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useCurrency } from "../lib/currency";
import {
  businessTypeOf,
  fitsProfiles,
  isFnBProfile,
  isRetailProfile,
} from "../lib/industry";

/** GET /api/v1/tenant/profile. The stored business type is a BusinessProfile id. */
export interface TenantProfileResponse {
  business_type: string;
  enabled_modules: string[];
}

export interface TenantContextValue {
  businessType: BusinessProfile;
  enabledModules: readonly string[];
  /** False until settings or the profile endpoint has answered. */
  ready: boolean;
  isRetail: boolean;
  isFnB: boolean;
  isElectronics: boolean;
  isFashion: boolean;
  allows: (profiles: readonly BusinessProfile[] | undefined) => boolean;
}

const TenantContext = createContext<TenantContextValue | null>(null);

export function TenantProvider({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const { settings } = useCurrency();
  const [remote, setRemote] = useState<TenantProfileResponse | null>(null);

  useEffect(() => {
    if (status !== "signed-in") return;
    let cancelled = false;
    apiGet<TenantProfileResponse>("/api/v1/tenant/profile")
      .then((row) => {
        if (!cancelled) setRemote(row);
      })
      .catch(() => {
        // Business settings already carry the same profile and module list.
      });
    return () => {
      cancelled = true;
    };
  }, [status, settings?.updated_at, settings?.business_profile]);

  const value = useMemo<TenantContextValue>(() => {
    const businessType = businessTypeOf(settings?.business_profile ?? remote?.business_type);
    const enabledModules = settings?.capabilities ?? remote?.enabled_modules ?? [];
    return {
      businessType,
      enabledModules,
      ready: settings !== null || remote !== null,
      isRetail: isRetailProfile(businessType),
      isFnB: isFnBProfile(businessType),
      isElectronics: businessType === "electronics_wholesale",
      isFashion: businessType === "retail_fashion",
      allows: (profiles) => fitsProfiles(businessType, profiles),
    };
  }, [settings, remote]);

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantContextValue {
  const value = useContext(TenantContext);
  if (value === null) throw new Error("TenantProvider is missing.");
  return value;
}
