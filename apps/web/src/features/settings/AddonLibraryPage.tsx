import {
  capabilitySpec,
  formatMoney,
  isCapability,
  rankAddons,
  type BillingAddon,
  type BillingCatalog,
  type BusinessSettings,
  type Capability,
} from "@ai-pos/shared-types";
import { useEffect, useMemo, useState } from "react";
import { ErrorNote, SearchField } from "../../components/ui/Field";
import { apiGet, apiPut } from "../../lib/api";
import { useCapabilities } from "../../lib/capabilities";
import { useCurrency } from "../../lib/currency";
import { errorMessage } from "../users/api";
import { presetSelection, sameSelection, toggleModule } from "./profileParts";

function moduleLabel(key: string): string {
  return isCapability(key) ? capabilitySpec(key).label : key;
}

function priceLines(addon: BillingAddon): string[] {
  const lines: string[] = [];
  if (addon.monthly_fils > 0) lines.push(`${formatMoney(addon.monthly_fils, "AED")} per month`);
  if (addon.one_time_fils > 0) {
    lines.push(
      addon.refundable
        ? `${formatMoney(addon.one_time_fils, "AED")} refundable deposit, charged once`
        : `${formatMoney(addon.one_time_fils, "AED")} one-time`,
    );
  }
  if (lines.length === 0) lines.push("No extra charge");
  return lines;
}

function switchedKeys(addon: BillingAddon): Capability[] {
  return addon.module_keys.filter(isCapability);
}

export function AddonLibraryPage() {
  const { settings, applySettings } = useCurrency();
  const { enabled, planned, profile } = useCapabilities();
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet<BillingCatalog>("/api/v1/billing/catalog")
      .then((next) => {
        if (!cancelled) {
          setCatalog(next);
          setLoadError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!cancelled) setLoadError(errorMessage(caught, "The add-on library could not be loaded."));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const published = useMemo(() => (catalog?.addons ?? []).filter((addon) => addon.active), [catalog]);
  const addons = useMemo(() => rankAddons(published, query), [published, query]);
  const current = useMemo(() => new Set<Capability>([...enabled, ...planned]), [enabled, planned]);

  const toggle = async (addon: BillingAddon, turnOn: boolean) => {
    if (settings === null || busyCode !== null) return;
    const keys = switchedKeys(addon);
    if (keys.length === 0) return;
    let next = new Set(current);
    for (const key of keys) next = toggleModule(next, key, turnOn);
    setBusyCode(addon.code);
    setError(null);
    setNotice(null);
    try {
      const preset = presetSelection(profile);
      const saved = await apiPut<BusinessSettings>("/api/v1/settings/profile", {
        business_profile: profile,
        capabilities: sameSelection(next, preset) ? null : [...next],
      });
      applySettings(saved);
      setNotice(
        turnOn
          ? `${addon.name} is on. People with access to it see its sections in the sidebar.`
          : `${addon.name} is off. Its sections are hidden from the sidebar.`,
      );
    } catch (caught) {
      setError(errorMessage(caught, `Could not update ${addon.name}.`));
    } finally {
      setBusyCode(null);
    }
  };

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4 p-4 md:p-6">
      <header>
        <h1 className="text-xl font-semibold">Add-ons</h1>
        <p className="mt-1 text-sm text-charcoal/60">
          Browse the add-on library and switch on the ones this store uses. Search matches the name and the description,
          and the closest name is listed first. Prices are in AED.
        </p>
      </header>
      <SearchField
        label="Search add-ons"
        placeholder="Search by name or description"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <ErrorNote message={loadError ?? error} />
      {notice ? <p className="text-sm text-charcoal/70">{notice}</p> : null}
      {catalog && addons.length === 0 ? (
        <p className="rounded-2xl border border-dashed border-line bg-white px-4 py-8 text-center text-sm text-charcoal/60">
          {query.trim() ? "No add-ons match that search." : "No add-ons are published yet."}
        </p>
      ) : null}
      <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-white">
        {addons.map((addon) => {
          const keys = switchedKeys(addon);
          const onCount = keys.filter((key) => enabled.has(key)).length;
          const checked = keys.length > 0 && onCount === keys.length;
          const mixed = onCount > 0 && onCount < keys.length;
          const busy = busyCode === addon.code;
          return (
            <li key={addon.id} className="flex items-start gap-3 p-4">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-accent"
                checked={checked}
                disabled={busyCode !== null || keys.length === 0 || settings === null}
                aria-busy={busy}
                aria-label={addon.name}
                ref={(node) => {
                  if (node) node.indeterminate = mixed;
                }}
                onChange={(event) => void toggle(addon, event.target.checked)}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-semibold">{addon.name}</p>
                  {checked ? (
                    <span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-accent">
                      On
                    </span>
                  ) : null}
                </div>
                <p className="mt-0.5 text-sm text-charcoal/70">{addon.description || "No description."}</p>
                <p className="mt-2 text-xs font-medium text-charcoal/80">{priceLines(addon).join(" · ")}</p>
                <p className="mt-1 text-xs text-charcoal/50">
                  {keys.length > 0 ? keys.map(moduleLabel).join(", ") : "Does not add a sidebar section."}
                </p>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
