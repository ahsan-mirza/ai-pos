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
  knownBusinessType,
} from "../lib/industry";

/** GET /api/v1/tenant/profile. The stored business type is a BusinessProfile id. */
export interface TenantProfileResponse {
  business_type: string;
  enabled_modules: string[];
}

export interface TenantContextValue {
  businessType: BusinessProfile;
  /** The id returned by the API, including values this portal does not recognize. */
  storedProfile: string | null;
  enabledModules: readonly string[];
  /** False until settings or the profile endpoint has answered. */
  ready: boolean;
  /** True once a supported business type has been read. Unknown ids stay false. */
  recognized: boolean;
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
    const storedProfile = settings?.business_profile ?? remote?.business_type ?? null;
    const known = knownBusinessType(storedProfile);
    const ready = settings !== null || remote !== null;
    const recognized = ready && known !== null;
    const businessType = businessTypeOf(storedProfile);
    const enabledModules = settings?.capabilities ?? remote?.enabled_modules ?? [];
    return {
      businessType,
      storedProfile,
      enabledModules,
      ready,
      recognized,
      isRetail: known !== null && isRetailProfile(known),
      isFnB: known !== null && isFnBProfile(known),
      isElectronics: known === "electronics_wholesale",
      isFashion: known === "retail_fashion",
      // Until the type is known, only pages with no industry allow-list stay visible.
      allows: (profiles) => (recognized ? fitsProfiles(known, profiles) : profiles === undefined),
    };
  }, [settings, remote]);

  return <TenantContext.Provider value={value}>{children}</TenantContext.Provider>;
}

export function useTenant(): TenantContextValue {
  const value = useContext(TenantContext);
  if (value === null) throw new Error("TenantProvider is missing.");
  return value;
}
