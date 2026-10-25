import type { BusinessSettings, OnboardingChecklist } from "@ai-pos/shared-types";
import { FlaskConical, ShieldAlert } from "lucide-react";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import { apiGet } from "../../lib/api";
import { portalHomePath } from "../../lib/portal-home";
import { useCanManageSettings, useCurrency } from "../../lib/currency";
import { GoLiveModal } from "./GoLiveModal";

interface PracticeState {
  /** The store is in practice mode: sample items, and test sales that Go live clears. */
  practice: boolean;
  checklist: OnboardingChecklist | null;
  refresh: () => void;
  openGoLive: () => void;
}

const PracticeContext = createContext<PracticeState>({
  practice: false,
  checklist: null,
  refresh: () => undefined,
  openGoLive: () => undefined,
});

export function PracticeProvider({ children }: { children: ReactNode }) {
  const { settings, applySettings } = useCurrency();
  const canManage = useCanManageSettings();
  const { pathname } = useLocation();
  const practice = settings?.practice_mode === true;
  const [checklist, setChecklist] = useState<OnboardingChecklist | null>(null);
  const [goLiveOpen, setGoLiveOpen] = useState(false);
  const [tick, setTick] = useState(0);

  const refresh = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!practice || !canManage) return;
    let cancelled = false;
    apiGet<OnboardingChecklist>("/api/v1/onboarding/checklist")
      .then((next) => {
        if (!cancelled) setChecklist(next);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [practice, canManage, pathname, tick]);

  useEffect(() => {
    if (!practice) return;
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [practice, refresh]);

  // Every page may be showing sample rows Go live just deleted, so start the portal over with fresh settings.
  const wentLive = useCallback(() => {
    setGoLiveOpen(false);
    apiGet<BusinessSettings>("/api/v1/settings")
      .then(applySettings)
      .catch(() => undefined)
      .finally(() => window.location.assign(portalHomePath()));
  }, [applySettings]);

  const value = useMemo<PracticeState>(
    () => ({ practice, checklist, refresh, openGoLive: () => setGoLiveOpen(true) }),
    [practice, checklist, refresh],
  );

  return (
    <PracticeContext.Provider value={value}>
      {children}
      {goLiveOpen && canManage ? (
        <GoLiveModal
          storeName={checklist?.store_name ?? settings?.legal_name ?? ""}
          trn={settings?.trn ?? null}
          taxAuthority={settings?.tax_authority ?? "fta"}
          openingStockUnits={checklist?.opening_stock_units ?? 0}
          onClose={() => setGoLiveOpen(false)}
          onLive={wentLive}
        />
      ) : null}
    </PracticeContext.Provider>
  );
}

export function usePractice(): PracticeState {
  return useContext(PracticeContext);
}

export function TaxPortalBanner() {
  const { settings } = useCurrency();
  if (settings?.tax_portal_pending !== true) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 md:px-6"
    >
      <ShieldAlert size={16} aria-hidden="true" className="shrink-0" />
      <p className="min-w-0 flex-1">
        <strong className="font-semibold">Tax portal is not connected.</strong> Practice stamps were removed. Invoices
        are validated locally and are not cleared with the authority.
      </p>
    </div>
  );
}

export function PracticeBanner() {
  const { practice, openGoLive } = usePractice();
  const canManage = useCanManageSettings();
  if (!practice) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-900 md:px-6"
    >
      <FlaskConical size={16} aria-hidden="true" className="shrink-0" />
      <p className="min-w-0 flex-1">
        <strong className="font-semibold">Practice mode.</strong> Sample items and test sales are cleared when you go
        live.
      </p>
      {canManage ? (
        <button
          type="button"
          onClick={openGoLive}
          className="rounded-full bg-amber-900 px-4 py-1 text-xs font-semibold text-white hover:bg-amber-950"
        >
          Go live
        </button>
      ) : null}
    </div>
  );
}
