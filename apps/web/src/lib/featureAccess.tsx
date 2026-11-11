import { useLocale } from "@ai-pos/ui";
import { useCurrency } from "./currency";
import { apiGet, onFeatureDenied } from "./api";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { PremiumUpgradeModal } from "../features/billing/PremiumUpgradeModal";

export interface FeatureAccess {
  feature_key: string;
  label: string;
  description: string;
  state:
    | "INCLUDED"
    | "TRIAL_INCLUDED"
    | "UPGRADE_REQUIRED"
    | "PLUGIN_REQUIRED"
    | "BUSINESS_TYPE_UNAVAILABLE"
    | "COUNTRY_UNAVAILABLE"
    | "FEATURE_DISABLED"
    | "SUBSCRIPTION_RESTRICTED"
    | "SWITCHED_OFF";
  current_plan: string | null;
  current_plan_name: string | null;
  required_plan: string | null;
  required_plan_name: string | null;
  price_fils: number | null;
  currency: string | null;
  price_published: boolean;
  custom_pricing: boolean;
  trial_available: boolean;
  plugin_code: string | null;
  plugin_name: string | null;
  benefits: string[];
}

const BLOCKS = new Set<FeatureAccess["state"]>([
  "UPGRADE_REQUIRED",
  "PLUGIN_REQUIRED",
  "COUNTRY_UNAVAILABLE",
  "FEATURE_DISABLED",
  "BUSINESS_TYPE_UNAVAILABLE",
  "SUBSCRIPTION_RESTRICTED",
]);

interface FeatureContextValue {
  ready: boolean;
  failed: boolean;
  get: (key: string) => FeatureAccess | undefined;
  open: (key: string) => void;
  reload: () => void;
}

const FeatureContext = createContext<FeatureContextValue | null>(null);

export function FeatureAccessProvider({ children }: { children: ReactNode }) {
  const { settings } = useCurrency();
  const [rows, setRows] = useState<FeatureAccess[]>([]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [openKey, setOpenKey] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);
  const revision = settings?.entitlement_revision ?? 0;

  const reload = useCallback(() => setReloadToken((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    apiGet<{ features: FeatureAccess[] }>("/api/v1/billing/features")
      .then((found) => {
        if (!cancelled) {
          setRows(found.features);
          setFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRows([]);
          setFailed(true);
        }
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [revision, reloadToken]);

  const open = useCallback((key: string) => setOpenKey(key), []);

  useEffect(() => onFeatureDenied(open), [open]);

  const value = useMemo<FeatureContextValue>(
    () => ({
      ready,
      failed,
      get: (key) => rows.find((row) => row.feature_key === key),
      open,
      reload,
    }),
    [ready, failed, rows, open, reload],
  );
  const selected = openKey ? rows.find((row) => row.feature_key === openKey) : undefined;

  return (
    <FeatureContext.Provider value={value}>
      {children}
      {selected && BLOCKS.has(selected.state) ? (
        <PremiumUpgradeModal feature={selected} onClose={() => setOpenKey(null)} onTrialStarted={reload} />
      ) : null}
    </FeatureContext.Provider>
  );
}

export function useFeatureAccess(featureKey: string): FeatureAccess | undefined {
  return useContext(FeatureContext)?.get(featureKey);
}

export function useFeatureActions(): Pick<FeatureContextValue, "open" | "ready" | "failed" | "reload" | "get"> {
  const context = useContext(FeatureContext);
  return {
    open: context?.open ?? (() => undefined),
    ready: context?.ready ?? false,
    failed: context?.failed ?? false,
    reload: context?.reload ?? (() => undefined),
    get: context?.get ?? (() => undefined),
  };
}

export function featureIsBlocked(feature: FeatureAccess | undefined): boolean {
  return feature !== undefined && BLOCKS.has(feature.state);
}

/** Renders the page when the published plan includes it. A direct URL opens the same modal as the sidebar. */
export function FeatureAccessGuard({ featureKey, children }: { featureKey: string; children: ReactNode }) {
  const feature = useFeatureAccess(featureKey);
  const { open, ready, failed, reload } = useFeatureActions();
  const { t } = useLocale();
  const dismissed = useRef(false);
  const blocked = featureIsBlocked(feature);

  useEffect(() => {
    dismissed.current = false;
  }, [featureKey]);

  useEffect(() => {
    if (!blocked || dismissed.current) return;
    open(featureKey);
  }, [blocked, featureKey, open]);

  if (!ready) return null;
  if (failed || !feature) {
    return (
      <section className="m-4 max-w-lg rounded-card border border-line bg-white p-6 md:m-6">
        <h1 className="text-xl font-semibold">{t("Plan access could not be confirmed.")}</h1>
        <button type="button" className="mt-4 text-sm font-semibold text-accent" onClick={reload}>
          {t("Try again")}
        </button>
      </section>
    );
  }
  if (!blocked) return children;
  return (
    <section className="m-4 max-w-lg rounded-card border border-line bg-white p-6 md:m-6">
      <h1 className="text-xl font-semibold">{feature?.label}</h1>
      <p className="mt-2 text-sm text-charcoal/70">{feature?.description}</p>
      <button
        type="button"
        className="mt-4 inline-flex h-10 items-center rounded-lg bg-accent px-4 text-sm font-semibold text-white"
        onClick={() => {
          dismissed.current = false;
          open(featureKey);
        }}
      >
        {feature?.state === "PLUGIN_REQUIRED" ? t("Explore add-ons") : t("View plans")}
      </button>
    </section>
  );
}
